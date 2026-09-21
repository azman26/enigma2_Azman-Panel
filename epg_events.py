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

try:
    from urllib.request import Request, urlopen
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
MISSING_EVENTS_REPORT_FILE = "/tmp/azmanpanel_epg_missing_events.json"


def _save_missing_events_report(names):
    # Diagnostyka: ktore kanaly z bukietu MIALY referencje, ale serwer nie
    # zwrocil dla nich zadnych eventow (brak w events.json albo bledna nazwa
    # w zrodle XMLTV) - odrozniamy to od kanalow bez referencji w ogole,
    # ktore juz sa widoczne w raporcie mappera (epg_mapper.py).
    try:
        parent = os.path.dirname(MISSING_EVENTS_REPORT_FILE)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        temporary = MISSING_EVENTS_REPORT_FILE + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(sorted(names), handle, ensure_ascii=False, indent=2)
        replace = getattr(os, "replace", os.rename)
        replace(temporary, MISSING_EVENTS_REPORT_FILE)
    except Exception:
        pass


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
    data = _config()
    if (
        data.get("enabled") is True
        and str(data.get("url") or "").startswith("https://")
        and str(data.get("token") or "").strip()
        and str(data.get("box_id") or "").strip()
    ):
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
            result = json.loads(response.read().decode("utf-8"))
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
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
        except Exception:
            continue
        for line in lines:
            line = line.strip()
            if not line.startswith("#SERVICE 4097:"):
                continue
            parts = line[len("#SERVICE "):].split(":")
            if len(parts) != 12:
                continue
            reference_fields = parts[1:10]
            name = parts[11].strip()
            if not name:
                continue
            dvb_reference = "1:" + ":".join(reference_fields)
            seen[name] = dvb_reference
    return list(seen.items())


def _describe_error(error):
    # Bez tego log pokazywal tylko "HTTPError" bez kodu statusu (403/404/429/
    # 503...), wiec kazda awaria wygladala identycznie i trzeba bylo recznie
    # odpytywac API, zeby ustalic prawdziwa przyczyne.
    detail = error.__class__.__name__
    status = getattr(error, "code", None)
    if status:
        detail += " status=%s" % status
        try:
            body = error.read()
            if body:
                text = body.decode("utf-8", "replace").strip()[:200]
                if text:
                    detail += " body=%s" % text
        except Exception:
            pass
    return detail


def _request_events(base_url, config, references, logger):
    url = _events_url(base_url)
    if not url:
        logger("events url could not be derived - check 'url' in epg_access.json")
        return {}
    payload = json.dumps({
        "box_id": str(config.get("box_id") or "").strip(),
        "references": references,
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
            result = json.loads(response.read().decode("utf-8"))
        finally:
            response.close()
        events = result.get("events") if isinstance(result, dict) else {}
        return events if isinstance(events, dict) else {}
    except HTTPError as error:
        if error.code == 403:
            _invalidate_and_retry_registration()
        logger("events request failed: %s" % _describe_error(error))
        return {}
    except Exception as error:
        logger("events request failed: %s" % _describe_error(error))
        return {}


def _to_event_tuples(raw_events):
    tuples = []
    for entry in raw_events or []:
        if not isinstance(entry, (list, tuple)) or len(entry) < 4:
            continue
        start, duration, title, desc = entry[0], entry[1], entry[2], entry[3]
        try:
            start = int(start)
            duration = int(duration)
        except (TypeError, ValueError):
            continue
        if duration <= 0:
            continue
        desc = str(desc or "")[:MAX_DESC_LEN]
        title = str(title or "")
        if not title:
            continue
        tuples.append((start, duration, title, desc[:240], desc, 0))
    return tuples


def import_events(logger=None, epgcache=None):
    """Glowny wpis: skanuje wlasne bukiety, pobiera eventy z prywatnego API
    i wstrzykuje je przez eEPGCache.importEvents(). Zwraca (channels, events)
    - liczbe kanalow z dopasowanymi eventami i sumaryczna liczbe wstrzykniete
    zdarzen, do logowania przez wywolujacego."""
    logger = logger or (lambda _message: None)
    if not available(logger):
        logger("EPG events: disabled - private API access not configured")
        return 0, 0

    channels = scan_bouquet_channels()
    if not channels:
        logger("EPG events: no AzmanPanel bouquet channels found")
        return 0, 0

    if epgcache is None:
        try:
            from enigma import eEPGCache
            epgcache = eEPGCache.getInstance()
        except Exception as error:
            logger("EPG events: eEPGCache unavailable: %s" % error)
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

    matched_channels = 0
    total_events = 0
    imported_references = set()
    batches = range(0, len(references), MAX_CHANNELS_PER_REQUEST)
    for batch_index, offset in enumerate(batches):
        if batch_index:
            time.sleep(1)
        batch = references[offset:offset + MAX_CHANNELS_PER_REQUEST]
        events_by_reference = _request_events(base_url, config, batch, logger)
        for reference, raw_events in events_by_reference.items():
            if reference in imported_references:
                continue
            event_tuples = _to_event_tuples(raw_events)
            if not event_tuples:
                continue
            try:
                epgcache.importEvents(reference, event_tuples)
                imported_references.add(reference)
                matched_channels += 1
                total_events += len(event_tuples)
            except Exception as error:
                logger("EPG events: importEvents failed reference=%s error=%s" % (reference, error))

    missing_names = sorted(
        name for reference, names in names_by_reference.items() if reference not in imported_references
        for name in names
    )
    if missing_names:
        _save_missing_events_report(missing_names)
        preview = ", ".join(missing_names[:10])
        if len(missing_names) > 10:
            preview += ", ..."
        logger("EPG events: no data for %d channel(s): %s (pelna lista: %s)" % (
            len(missing_names), preview, MISSING_EVENTS_REPORT_FILE))

    logger("EPG events: imported %d events across %d channels" % (total_events, matched_channels))
    return matched_channels, total_events


def import_events_async(logger=None):
    """Odpala import_events() w tle - do wolania zaraz po zapisaniu bukietu
    albo z harmonogramu, bez blokowania GUI/watku wywolujacego."""
    thread = threading.Thread(target=lambda: import_events(logger=logger), name="AzmanPanelEpgEventsImport")
    thread.daemon = True
    thread.start()
    return thread
