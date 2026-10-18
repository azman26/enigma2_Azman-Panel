# -*- coding: utf-8 -*-
"""Pobiera i wstrzykuje eventy EPG (nie tylko referencje) dla kanalow z juz
wygenerowanych bukietow AzmanPanel. Zrodlem prawdy "co potrzebuje EPG" sa same
pliki bukietow na dysku - nie ma osobnego trwalego cache do utrzymywania."""
from __future__ import print_function

import glob
import json
import os
import threading
import time
import uuid

from .epg_private import registration_lock
from .mainthread import call_in_main_thread
from .epg_jobs import ImportQueue
from .epg_validation import read_json, valid_reference
from urllib.request import HTTPRedirectHandler, build_opener

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def urlopen(request, timeout=30):
    return build_opener(_NoRedirect()).open(request, timeout=timeout)

try:
    from urllib.request import Request
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import Request, urlopen, HTTPError


ACCESS_FILE = "/etc/AzmanPanel/epg_access.json"
# Ten sam mechanizm samorejestracji co w epg_private.py - zeby import_events()
# tez samo-naprawialo sie, niezaleznie od tego, czy proces mapowania
# referencji zdazyl juz zarejestrowac ten box, czy nie (np. timer 12h moglby
# odpalic sie jako pierwszy, przed jakimkolwiek zapisem bukietu).
REGISTER_URL = "https://www.topolowa4.pl/api/register-epg-client.php"
REGISTER_APP_KEY = "azman-epg-client-2026"
EPG_MAP_URL = "https://www.topolowa4.pl/api/epg-map.php"
REGISTER_RETRY_SECONDS = 3600
BOUQUET_GLOB = "/etc/enigma2/userbouquet.azmanpanel_*"
MAX_CHANNELS_PER_REQUEST = 25
MAX_DESC_LEN = 400
_SOURCE_STATUS = {}
MISSING_EVENTS_REPORT_FILE = "/tmp/azmanpanel_epg_missing_events.json"


def _save_missing_events_report(names):
    import tempfile
    temporary = None
    try:
        parent = os.path.dirname(MISSING_EVENTS_REPORT_FILE)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        fd, temporary = tempfile.mkstemp(prefix=".azman-epg-missing-", dir=parent or ".")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(sorted(names), handle, ensure_ascii=False, indent=2)
        os.replace(temporary, MISSING_EVENTS_REPORT_FILE)
    except Exception:
        pass
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def _config():
    try:
        try:
            os.chmod(ACCESS_FILE, 0o600)
        except Exception:
            pass
        with open(ACCESS_FILE, "r") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_config(data):
    try:
        directory = os.path.dirname(ACCESS_FILE)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        temporary = ACCESS_FILE + ".tmp"
        with open(temporary, "w") as handle:
            json.dump(data, handle)
        os.chmod(temporary, 0o600)
        replace = getattr(os, "replace", os.rename)
        replace(temporary, ACCESS_FILE)
    except Exception:
        pass


def _ensure_registered(logger):
    if _registered(_config()):
        return
    with registration_lock(ACCESS_FILE):
        _ensure_registered_locked(logger)


def _registered(data):
    return bool(
        data.get("enabled") is True
        and str(data.get("url") or "").startswith("https://")
        and str(data.get("token") or "").strip()
        and str(data.get("box_id") or "").strip()
    )


def _ensure_registered_locked(logger):
    data = _config()
    if _registered(data):
        return
    last_attempt = float(data.get("_register_attempted_at") or 0)
    if time.time() - last_attempt < REGISTER_RETRY_SECONDS:
        return
    box_id = str(data.get("box_id") or "").strip()
    if not box_id:
        box_id = uuid.uuid4().hex
        data["box_id"] = box_id
        _save_config(data)
    try:
        payload = json.dumps({"box_id": box_id}).encode("utf-8")
        request = Request(REGISTER_URL, data=payload, headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Azman-App-Key": REGISTER_APP_KEY,
            "User-Agent": "AzmanPanel-EPGRegister/1",
        })
        response = urlopen(request, timeout=15)
        try:
            result = read_json(response)
        finally:
            response.close()
        token = str(result.get("token") or "").strip()
        if not token:
            raise ValueError("empty token in response")
        data.update({
            "enabled": True, "url": EPG_MAP_URL, "token": token,
            "box_id": box_id, "timeout": 12,
        })
        data.pop("_register_attempted_at", None)
        _save_config(data)
        logger("self-registration succeeded box_id=%s" % box_id)
    except Exception as error:
        data["_register_attempted_at"] = time.time()
        _save_config(data)
        logger("self-registration failed: %s" % _describe_error(error))


def _invalidate_and_retry_registration():
    data = _config()
    data["enabled"] = False
    data.pop("token", None)
    data.pop("_register_attempted_at", None)
    _save_config(data)


def available(logger=None):
    _ensure_registered(logger or (lambda _message: None))
    data = _config()
    return bool(
        data.get("enabled") is True
        and str(data.get("url") or "").startswith("https://")
        and str(data.get("token") or "").strip()
        and str(data.get("box_id") or "").strip()
    )


def _events_url(base_url):
    suffix = "epg-map.php"
    base_url = str(base_url or "")
    if base_url.endswith(suffix):
        return base_url[: -len(suffix)] + "epg-events.php"
    return ""


def scan_bouquet_channels(pattern=None):
    """Zwraca liste (name, dvb_reference) wyciagnieta z wpisow #SERVICE 4097:...
    juz zapisanych w bukietach - dvb_reference to pelna 10-polowa referencja
    "1:flags:stype:sid:tsid:onid:namespace:parent_sid:parent_tsid" gotowa dla
    eEPGCache.importEvents()."""
    pattern = pattern or BOUQUET_GLOB
    seen = {}
    for path in sorted(glob.glob(pattern)):
        filename = os.path.basename(path)
        if not filename.startswith("userbouquet.azmanpanel_") or not filename.endswith((".tv", ".radio")):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
        except Exception:
            continue
        for line in lines:
            line = line.strip()
            if not line.startswith("#SERVICE "):
                continue
            parts = line[len("#SERVICE "):].split(":")
            if len(parts) != 12 or parts[0] not in ("4097", "5002"):
                continue
            reference_fields = parts[1:10]
            name = parts[11].strip()
            if not name or not valid_reference(":".join(reference_fields)) or all(int(v, 16) == 0 for v in reference_fields[2:6]):
                continue
            dvb_reference = "1:" + ":".join(reference_fields)
            seen[(name, dvb_reference)] = True
    return list(seen)


def _describe_error(error):
    # Bez tego log pokazywal tylko "HTTPError" bez kodu statusu (403/404/429/
    # 503...), wiec kazda awaria wygladala identycznie i trzeba bylo recznie
    # odpytywac API, zeby ustalic prawdziwa przyczyne.
    detail = error.__class__.__name__
    status = getattr(error, "code", None)
    if status:
        detail += " status=%s" % status
    return detail


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
        "User-Agent": "AzmanPanel-EPGEvents/1",
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
        return {key: value for key, value in events.items() if key in set(references) and isinstance(value, list)}
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
            _invalidate_and_retry_registration()
        logger("events request failed: %s" % _describe_error(error))
        return None
    except Exception as error:
        logger("events request failed: %s" % _describe_error(error))
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
    i wstrzykuje je przez eEPGCache.importEvents(). Zwraca (channels, events)
    - liczbe kanalow z dopasowanymi eventami i sumaryczna liczbe wstrzykniete
    zdarzen, do logowania przez wywolujacego."""
    logger = logger or (lambda _message: None)
    if not available(logger):
        logger("EPG events: disabled - private API access not configured")
        return 0, 0

    channels = scan_bouquet_channels(pattern)
    if not channels:
        logger("EPG events: no AzmanPanel bouquet channels found")
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

    def apply_events():
        return _apply_events(pending, names_by_reference, epgcache, logger, failed_references)

    if epgcache is not None:
        return apply_events()
    call_in_main_thread(apply_events, logger=logger)
    return len(pending), sum(len(event_tuples) for _reference, event_tuples in pending)


def _apply_events(pending, names_by_reference, epgcache, logger, failed_references=None):
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
    for reference, event_tuples in pending:
        try:
            epgcache.importEvents(reference, event_tuples)
            imported_references.add(reference)
            matched_channels += 1
            total_events += len(event_tuples)
        except Exception as error:
            logger("EPG events: importEvents failed reference=%s error=%s" % (reference, error))

    missing_names = sorted(
        name for reference, names in names_by_reference.items() if reference not in imported_references and reference not in failed_references
        for name in names
    )
    if missing_names:
        _save_missing_events_report(missing_names)
        preview = ", ".join(missing_names[:10])
        if len(missing_names) > 10:
            preview += ", ..."
        logger("EPG events: no data for %d channel(s): %s (pelna lista: %s)" % (
            len(missing_names), preview, MISSING_EVENTS_REPORT_FILE))

    if not missing_names and not failed_references:
        try:
            os.unlink(MISSING_EVENTS_REPORT_FILE)
        except OSError:
            pass
    if failed_references:
        logger("EPG events: transport failed for %d references; not classified as missing EPG" % len(failed_references))
    try:
        import tempfile
        status_path = MISSING_EVENTS_REPORT_FILE.replace("missing_events", "status")
        status = {"attempted_at": int(time.time()), "imported_channels": matched_channels,
                  "imported_events": total_events, "failed_references": len(failed_references),
                  "missing_channels": len(missing_names), "source": dict(_SOURCE_STATUS)}
        try:
            with open(status_path, "r", encoding="utf-8") as handle:
                previous = json.loads(handle.read(8192))
            status["last_success_at"] = int(previous.get("last_success_at") or 0)
        except (OSError, ValueError, TypeError):
            status["last_success_at"] = 0
        if not failed_references and matched_channels == len(pending):
            status["last_success_at"] = status["attempted_at"]
        fd, temporary = tempfile.mkstemp(prefix=".azman-epg-", dir=os.path.dirname(status_path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(status, handle)
            os.replace(temporary, status_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    except Exception:
        pass

    logger("EPG events: imported %d events across %d channels" % (total_events, matched_channels))
    return matched_channels, total_events


_IMPORT_QUEUE = ImportQueue()

def import_events_async(logger=None, pattern=None):
    return _IMPORT_QUEUE.submit(import_events, logger=logger, pattern=pattern)
