# -*- coding: utf-8 -*-
"""Pobiera i wstrzykuje eventy EPG (nie tylko referencje) dla kanalow z juz
wygenerowanych bukietow AzmanFreeTvPlayer. Zrodlem prawdy "co potrzebuje EPG"
sa same pliki bukietow na dysku - nie ma osobnego trwalego cache."""
from __future__ import print_function

import glob
import json
import os
import time

from . import epg_access
from .mainthread import call_in_main_thread
from .epg_jobs import ImportQueue
from .epg_validation import read_json, valid_reference
from .epg_profile import EPG_EXCLUDED_PROVIDERS
from .epg_reports import merge_report, read_state
from .private_storage import atomic_json

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import Request, urlopen, HTTPError


from .epg_http_transport import private_urlopen as urlopen

from .epg_profile import BOUQUET_PREFIX, REPORT_PREFIX, PLUGIN_LABEL
BOUQUET_GLOB = "/etc/enigma2/" + BOUQUET_PREFIX + "*"
# bouquets.py wybiera 4097 (gstreamer) albo 5002 (ExtePlayer3, providerzy z
# force_exteplayer3=True np. Avios, Channelbox) - obie postacie trzeba
# rozpoznawac, inaczej kanaly graczy wymuszajacych ExtePlayer3 nigdy nie
# dostana wstrzykiwanych eventow (byl to realny, cichy bug).
KNOWN_SERVICE_TYPES = ("4097", "5002")
MAX_CHANNELS_PER_REQUEST = 25
MAX_DESC_LEN = 400
_SOURCE_STATUS = {}
MISSING_EVENTS_REPORT_FILE = REPORT_PREFIX + "_missing_events.json"


def _config():
    return epg_access.load_config()


def available(logger=None):
    return epg_access.available(logger)


def _events_url(base_url):
    suffix = "epg-map.php"
    base_url = str(base_url or "")
    if base_url.endswith(suffix):
        return base_url[: -len(suffix)] + "epg-events.php"
    return ""


def _empty_reference(reference_fields):
    # Kanal bez mapowania EPG ma w bukiecie "4097:0:1:0:0:0:0:0:0:0" - wszystkie
    # takie kanaly zlewaly sie w jedna referencje, szly do serwera i trafialy do
    # raportu "brak eventow" (sa juz w raporcie mappera jako brak referencji).
    try:
        return all(int(value or "0", 16) == 0 for value in reference_fields[2:6])
    except ValueError:
        return True


def scan_bouquet_channels(pattern=None):
    """Zwraca liste (name, dvb_reference) wyciagnieta z wpisow #SERVICE 4097:...
    juz zapisanych w bukietach - dvb_reference to pelna 10-polowa referencja
    "1:flags:stype:sid:tsid:onid:namespace:parent_sid:parent_tsid" gotowa dla
    eEPGCache.importEvents()."""
    pattern = pattern or BOUQUET_GLOB
    seen = {}
    for path in sorted(glob.glob(pattern)):
        filename = os.path.basename(path)
        if not filename.startswith(BOUQUET_PREFIX) or not filename.endswith((".tv", ".radio")):
            continue
        if os.path.basename(path) in (
            BOUQUET_PREFIX + "%s.tv" % provider_id
            for provider_id in EPG_EXCLUDED_PROVIDERS
        ):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
        except Exception:
            continue
        for line_index, line in enumerate(lines):
            line = line.strip()
            if not line.startswith("#SERVICE "):
                continue
            parts = line[len("#SERVICE "):].split(":")
            if len(parts) not in (11, 12) or parts[0] not in KNOWN_SERVICE_TYPES:
                continue
            reference_fields = parts[1:10]
            name = parts[11].strip() if len(parts) == 12 else ""
            if line_index + 1 < len(lines) and lines[line_index + 1].startswith("#DESCRIPTION "):
                name = lines[line_index + 1][len("#DESCRIPTION "):].strip() or name
            if not name or not valid_reference(":".join(reference_fields)) or _empty_reference(reference_fields):
                continue
            dvb_reference = "1:" + ":".join(reference_fields)
            seen[(name, dvb_reference)] = True
    return list(seen)


def _request_events(base_url, config, references, logger):
    url = _events_url(base_url)
    if not url:
        logger("events url could not be derived - check 'url' in epg_access.json")
        return None
    payload = json.dumps({
        "box_id": str(config.get("box_id") or "").strip(),
        "references": references,
        "window_days": 7,
    }).encode("utf-8")
    headers = {
        "Authorization": "Bearer %s" % str(config.get("token") or "").strip(),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Cache-Control": "no-store",
        "User-Agent": "AzmanFreeTV-EPGEvents/1",
    }
    try:
        request = Request(url, data=payload, headers=headers)
        response = urlopen(request, timeout=int(config.get("timeout") or 12))
        try:
            result = read_json(response)
        finally:
            response.close()
        _SOURCE_STATUS.clear()
        _SOURCE_STATUS.update({key: str(result.get(key) or "")[:80] for key in ("generation", "updated_at")})
        events = result.get("events") if isinstance(result, dict) else None
        if not isinstance(events, dict):
            return None
        requested = set(references)
        return {reference: entries for reference, entries in events.items()
                if reference in requested and isinstance(entries, list)}
    except ValueError as error:
        if str(error) == "EPG response too large" and len(references) > 1:
            middle = len(references) // 2
            first = _request_events(base_url, config, references[:middle], logger)
            second = _request_events(base_url, config, references[middle:], logger)
            if first is None or second is None:
                return None
            first.update(second)
            return first
        logger("events request failed: ValueError")
        return None
    except HTTPError as error:
        if error.code == 403:
            epg_access.invalidate_registration()
        logger("events request failed: %s" % epg_access.describe_error(error))
        return None
    except Exception as error:
        logger("events request failed: %s" % epg_access.describe_error(error))
        return None


def _to_event_tuples(raw_events):
    tuples = []
    if not isinstance(raw_events, (list, tuple)):
        return tuples
    for entry in raw_events[:8192]:
        if not isinstance(entry, (list, tuple)) or len(entry) < 4:
            continue
        start, duration, title, desc = entry[0], entry[1], entry[2], entry[3]
        try:
            start = int(start)
            duration = int(duration)
        except (TypeError, ValueError, OverflowError):
            continue
        if not (0 <= start <= 2147483647 and 0 < duration <= 7 * 86400 and start + duration <= 2147483647):
            continue
        desc = str(desc or "")[:MAX_DESC_LEN]
        title = str(title or "")[:512]
        if not title:
            continue
        tuples.append((start, duration, title, desc[:240], desc, 0))
    return tuples


def import_events(logger=None, epgcache=None, pattern=None):
    """Glowny wpis: skanuje wlasne bukiety, pobiera eventy z prywatnego API
    i wstrzykuje je przez eEPGCache.importEvents(). Zwraca (channels, events).

    pattern: None = pelny skan wszystkich bukietow AzmanFreeTvPlayer (tak
    dziala okresowy timer co 12h i import przy starcie Enigmy2 - zapewnia,
    ze wszystko zostaje odswiezone nawet jesli akurat zaden bukiet nie byl
    ostatnio generowany). Konkretna sciezka pliku = tylko kanaly z JEDNEGO,
    wlasnie zapisanego bukietu - szybszy, tanszy w zapytaniach import od razu
    po wygenerowaniu jednego providera, bez czekania na pelny skan."""
    logger = logger or (lambda _message: None)
    _SOURCE_STATUS.clear()
    if not available(logger):
        logger("EPG events: disabled - private API access not configured")
        return 0, 0

    scope_channels = {}
    for path in sorted(glob.glob(pattern or BOUQUET_GLOB)):
        rows = scan_bouquet_channels(path)
        filename = os.path.basename(path)
        if filename.startswith(BOUQUET_PREFIX) and filename.endswith(('.tv', '.radio')):
            scope = filename[len(BOUQUET_PREFIX):].rsplit('.', 1)[0]
            group = scope_channels.setdefault(scope, {})
            for name, reference in rows:
                group.setdefault(reference, []).append(name)
    channels = [(name, reference) for group in scope_channels.values()
                for reference, names in group.items() for name in names]
    if not channels:
        if scope_channels or pattern is None:
            # No native EPG calls are needed for an empty scope. Still clear
            # reports/status for removed channels and deleted bouquets.
            _apply_events([], {}, object(), logger, scope_channels=scope_channels,
                          full_scan=pattern is None, source_status={})
        logger("EPG events: no %s bouquet channels found" % PLUGIN_LABEL)
        return 0, 0

    config = _config()
    base_url = str(config.get("url") or "")
    # events.json jest teraz kluczowany bezposrednio referencja DVB (ta sama
    # postac, ktora bukiet juz ma w linii #SERVICE) zamiast nazwy kanalu -
    # eliminuje cale zgadywanie wariantow nazw (HD/sufiksy regionalne/pisownia),
    # bo referencja jednoznacznie identyfikuje kanal po obu stronach.
    names_by_reference = {}
    for name, reference in channels:
        names_by_reference.setdefault(reference, []).append(name)
    references = list(names_by_reference.keys())

    # Zapytania HTTP ida w biezacym watku (w tle), a samo wstrzykniecie do
    # eEPGCache - w glownym watku Enigmy2 (patrz mainthread.py).
    pending = []
    failed_references = set()
    fetched_references = set()
    batches = range(0, len(references), MAX_CHANNELS_PER_REQUEST)
    for batch_index, offset in enumerate(batches):
        if batch_index:
            time.sleep(1)
        batch = references[offset:offset + MAX_CHANNELS_PER_REQUEST]
        events_by_reference = _request_events(base_url, config, batch, logger)
        if events_by_reference is None:
            failed_references.update(batch)
            continue
        for reference, raw_events in events_by_reference.items():
            if reference in fetched_references:
                continue
            event_tuples = _to_event_tuples(raw_events)
            if not event_tuples:
                continue
            fetched_references.add(reference)
            pending.append((reference, event_tuples))

    source_status = dict(_SOURCE_STATUS)
    def apply_events():
        return _apply_events(pending, names_by_reference, epgcache, logger, failed_references,
                             scope_channels, pattern is None, source_status)

    if epgcache is not None:
        return apply_events()
    call_in_main_thread(apply_events, logger=logger)
    return len(pending), sum(len(event_tuples) for _reference, event_tuples in pending)


def _apply_events(pending, names_by_reference, epgcache, logger, failed_references=None,
                  scope_channels=None, full_scan=False, source_status=None):
    failed_references = failed_references or set()
    if epgcache is None:
        try:
            from enigma import eEPGCache
            epgcache = eEPGCache.getInstance()
        except Exception as error:
            logger("EPG events: eEPGCache unavailable: %s" % error)
            return 0, 0
    matched_channels = 0
    total_events = 0
    imported_references = set()
    apply_failed = set()
    for reference, event_tuples in pending:
        try:
            epgcache.importEvents(reference, event_tuples)
            imported_references.add(reference)
            matched_channels += 1
            total_events += len(event_tuples)
        except Exception as error:
            apply_failed.add(reference)
            logger("EPG events: importEvents failed reference=%s error=%s" % (reference, error))

    missing_names = sorted(
        name for reference, names in names_by_reference.items() if reference not in imported_references
        and reference not in failed_references and reference not in apply_failed
        for name in names
    )
    scope_channels = scope_channels if scope_channels is not None else {'__legacy__': names_by_reference}
    try:
        updates = {}
        for scope, group in scope_channels.items():
            updates[scope] = {reference: (None if reference in failed_references or reference in apply_failed
                else [] if reference in imported_references else names) for reference, names in group.items()}
        merge_report(MISSING_EVENTS_REPORT_FILE, updates, 'events',
                     active_scopes=set(scope_channels) if full_scan else None)
    except Exception as error:
        logger('EPG events: report not saved error=%s' % type(error).__name__)
    if missing_names:
        preview = ", ".join(missing_names[:10])
        if len(missing_names) > 10:
            preview += ", ..."
        logger("EPG events: no data for %d channel(s): %s (pelna lista: %s)" % (
            len(missing_names), preview, MISSING_EVENTS_REPORT_FILE))

    if failed_references:
        logger("EPG events: transport failed for %d references; not classified as missing EPG" % len(failed_references))
    try:
        status_path = MISSING_EVENTS_REPORT_FILE.replace("missing_events", "status")
        status = {"attempted_at": int(time.time()), "imported_channels": matched_channels,
                  "imported_events": total_events, "failed_references": len(failed_references),
                  "failed_imports": len(apply_failed),
                  "missing_channels": len(missing_names), "source": dict(source_status if source_status is not None else _SOURCE_STATUS),
                  "requested_channels": len(names_by_reference)}
        complete = bool(names_by_reference) and not failed_references and matched_channels == len(names_by_reference)
        status["status"] = ("success" if complete else "partial" if matched_channels else
                            "failed" if failed_references or pending else "no_data")
        previous = {}
        try:
            previous = read_state(status_path) or {}
            if not isinstance(previous, dict):
                raise ValueError('Invalid EPG status')
            status["last_success_at"] = int(previous.get("last_success_at") or 0)
        except (OSError, ValueError, TypeError):
            previous = {}
            status["last_success_at"] = 0
        if complete:
            status["last_success_at"] = status["attempted_at"]
        scoped_status = previous.get('scopes', {}) if isinstance(previous.get('scopes'), dict) else {}
        if full_scan:
            scoped_status = {key: value for key, value in scoped_status.items() if key in scope_channels}
        for scope, group in scope_channels.items():
            count = sum(reference in imported_references for reference in group)
            failures = sum(reference in failed_references or reference in apply_failed for reference in group)
            last_success = scoped_status.get(scope, {}).get('last_success_at', 0)
            scoped_status[scope] = {'attempted_at': status['attempted_at'], 'requested_channels': len(group),
                'imported_channels': count, 'failed_references': failures,
                'missing_channels': sum(reference not in imported_references and reference not in failed_references
                    and reference not in apply_failed for reference in group),
                'source': status['source'], 'last_success_at': status['attempted_at']
                    if group and count == len(group) and not failures else last_success}
        status['scopes'] = scoped_status
        status['scope'] = 'all' if full_scan else list(scope_channels)
        atomic_json(status_path, status)
    except Exception:
        pass

    logger("EPG events: imported %d events across %d channels" % (total_events, matched_channels))
    return matched_channels, total_events


_IMPORT_QUEUE = ImportQueue()

def import_events_async(logger=None, pattern=None):
    return _IMPORT_QUEUE.submit(import_events, logger=logger, pattern=pattern)
