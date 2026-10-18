"""Opt-in EPG for third-party IPTV bouquets, using the owner's XML mapping API."""
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import unquote, urlsplit

from .backups import ANY_BOUQUET, BackupStore
from .epg_jobs import ImportQueue
from .epg_private import PrivateEpgApiClient
from .epg_validation import valid_reference
from . import epg_events
from .mainthread import call_in_main_thread

_queue = ImportQueue()
_last_signature = None
_success_signature = None
_last_attempt = 0
_last_success = 0
MAX_BOUQUETS = 1000
MAX_CHANNELS = 10000
MAX_BYTES = 24 * 1024 * 1024
STATUS_FILE = "/tmp/azmanpanel_external_epg_status.json"


def save_status(status):
    try:
        BackupStore._write(Path(STATUS_FILE), json.dumps(status).encode("utf-8"))
    except (OSError, ValueError):
        pass


def scan(etc="/etc"):
    directory = Path(etc) / "enigma2"
    snapshots, records, reserved = {}, [], set()
    total = 0
    for path in sorted(directory.glob("userbouquet.*")):
        if not ANY_BOUQUET.fullmatch(path.name) or path.is_symlink():
            continue
        raw = BackupStore._read(path)
        total += len(raw)
        if total > MAX_BYTES or len(snapshots) >= MAX_BOUQUETS:
            raise ValueError("IPTV bouquet scan limit exceeded")
        try:
            lines = raw.decode("utf-8").splitlines(keepends=True)
        except UnicodeError:
            continue
        own = path.name.startswith(("userbouquet.azmanpanel_", "userbouquet.azmanfreetvplayer_"))
        snapshots[path.name] = raw
        for offset, line in enumerate(lines):
            if not line.startswith("#SERVICE "):
                continue
            parts = line[9:].rstrip("\r\n").split(":", 11)
            if len(parts) < 10 or not valid_reference(":".join(parts[1:10])):
                continue
            reference = "1:" + ":".join(parts[1:10])
            try:
                parsed = urlsplit(unquote(parts[10])) if len(parts) >= 11 else None
                is_iptv = parsed is not None and parsed.scheme in ("http", "https") and bool(parsed.netloc)
            except ValueError:
                is_iptv = False
            if not is_iptv or own:
                reserved.add(reference)
                continue
            name = parts[11].strip() if len(parts) == 12 else ""
            if not name and offset + 1 < len(lines) and lines[offset + 1].startswith("#DESCRIPTION "):
                name = lines[offset + 1][13:].strip()
            if not name:
                continue
            records.append({"file": path.name, "line": offset, "parts": parts, "name": unquote(name), "reference": reference})
            if len(records) > MAX_CHANNELS:
                raise ValueError("Too many IPTV channels")
    signature = tuple((name, hashlib.sha256(data).hexdigest()) for name, data in sorted(snapshots.items()))
    return snapshots, records, reserved, signature


def plan(records, mappings, reserved):
    uses = {}
    for record in records:
        source = mappings.get(record["name"], "")
        uses.setdefault(record["reference"], set()).add(source)
    result = []
    for record in records:
        source = mappings.get(record["name"], "")
        if not valid_reference(source[2:] if source.startswith("1:") else ""):
            continue
        current = record["reference"]
        nonzero = any(int(x, 16) for x in current.split(":")[3:7])
        reusable = nonzero and uses[current] == {source} and (current not in reserved or current == source)
        result.append(dict(record, source=source, target=current if reusable else source))
    return result


def update_bouquets(etc, snapshots, assignments, enabled=None):
    changes = {}
    for record in assignments:
        if record["target"] == record["reference"]:
            continue
        lines = changes.setdefault(record["file"], snapshots[record["file"]].decode("utf-8").splitlines(keepends=True))
        parts = list(record["parts"])
        parts[1:10] = record["target"].split(":")[1:]
        original = lines[record["line"]]
        ending = "\r\n" if original.endswith("\r\n") else "\n" if original.endswith("\n") else ""
        lines[record["line"]] = "#SERVICE " + ":".join(parts) + ending
    if not changes:
        return assignments, 0
    # Include the exact external files in the existing private, restorable backups.
    BackupStore(etc).create(extra_bouquets=set(changes))
    skipped, changed = set(), 0
    for name, lines in changes.items():
        if enabled is not None and not enabled():
            skipped.update(changes)
            break
        path = Path(etc) / "enigma2" / name
        if path.is_symlink() or BackupStore._read(path) != snapshots[name]:
            skipped.add(name)
            continue
        BackupStore._write(path, "".join(lines).encode("utf-8"))
        changed += 1
    return [r for r in assignments if r["file"] not in skipped], changed


def import_external(logger=None, pattern=None, etc="/etc", force=False, enabled=None):
    global _last_signature, _success_signature, _last_attempt, _last_success
    logger = logger or (lambda _: None)
    if enabled is not None and not enabled():
        return
    snapshots, records, reserved, signature = scan(etc)
    now = time.time()
    if not force:
        if signature == _success_signature and now - _last_success < 12 * 3600:
            return
        if signature == _last_signature and now - _last_attempt < 1800:
            return
    _success_signature = None
    _last_attempt = now
    _last_signature = signature
    if not records:
        return
    mapping_failed = [False]
    def mapping_log(message):
        if "failed" in message.lower():
            mapping_failed[0] = True
        logger(message)
    mapper = PrivateEpgApiClient(str(Path(etc) / "AzmanPanel" / "epg_access.json"), logger=mapping_log)
    names = {r["name"] for r in records}
    candidates = {name: [name] + ([] if name.lower().endswith(".pl") else [name + ".pl"]) for name in names}
    matches = mapper.resolve([candidate for values in candidates.values() for candidate in values])
    mappings = {}
    for name, values in candidates.items():
        references = {matches[value] for value in values if valid_reference(matches.get(value))}
        if len(references) == 1:
            mappings[name] = "1:" + references.pop()
    assignments = plan(records, mappings, reserved)
    if not assignments:
        logger("External IPTV EPG: no unambiguous mappings")
        save_status({"attempted_at": int(now), "last_success_at": int(_last_success),
            "scanned_channels": len(records), "matched_channels": 0, "unmatched_channels": len(records),
            "failed_references": int(mapping_failed[0])})
        return
    if enabled is not None and not enabled():
        return
    by_source = {}
    for record in assignments:
        by_source.setdefault(record["source"], set()).add(record["target"])
    fetched, failed = {}, 0
    config = epg_events._config()
    references = list(by_source)
    for offset in range(0, len(references), epg_events.MAX_CHANNELS_PER_REQUEST):
        if enabled is not None and not enabled():
            return
        if offset:
            time.sleep(1)
        batch = references[offset:offset + epg_events.MAX_CHANNELS_PER_REQUEST]
        events = epg_events._request_events(config.get("url", ""), config, batch, logger)
        if events is None:
            failed += len(batch)
            continue
        for source, raw in events.items():
            tuples = epg_events._to_event_tuples(raw)
            if tuples:
                fetched[source] = tuples

    # Never change a service reference without usable EPG already downloaded.
    eligible = [record for record in assignments if record["source"] in fetched]
    if enabled is not None and not enabled():
        return
    eligible_count = len(eligible)
    eligible, changed = update_bouquets(etc, snapshots, eligible, enabled=enabled)
    concurrent_edit = len(eligible) != eligible_count
    pending = list({record["target"]: fetched[record["source"]] for record in eligible}.items())
    completed_signature = scan(etc)[3]

    def apply():
        global _last_success, _success_signature
        if enabled is not None and not enabled():
            return
        from enigma import eDVBDB, eEPGCache
        if changed:
            eDVBDB.getInstance().reloadBouquets()
        cache = eEPGCache.getInstance()
        imported, native_failed = 0, 0
        for target, tuples in pending:
            try:
                cache.importEvents(target, tuples)
                imported += 1
            except Exception as error:
                native_failed += 1
                logger("External IPTV EPG import failed: " + type(error).__name__)
        logger("External IPTV EPG: scanned=%d matched=%d imported=%d changed_bouquets=%d failed=%d" %
               (len(records), len(assignments), len(pending), changed, failed))
        if not failed and not mapping_failed[0] and not native_failed and not concurrent_edit:
            _last_success = now
            _success_signature = completed_signature
        save_status({"attempted_at": int(now), "last_success_at": int(_last_success),
            "scanned_channels": len(records), "matched_channels": len(assignments),
            "unmatched_channels": len(records) - len(assignments), "modified_bouquets": changed,
            "imported_channels": imported, "failed_references": failed + native_failed,
            "mapping_failed": int(mapping_failed[0])})

    call_in_main_thread(apply, logger=logger)
    _last_signature = completed_signature


def import_external_async(logger=None, force=False, enabled=None):
    return _queue.submit(lambda logger=None, pattern=None: import_external(logger=logger, force=force, enabled=enabled), logger=logger)


REPORT_FILE = "/tmp/azmanpanel_iptv_audit.txt"
_repair_queue = ImportQueue()


def audit_external(logger=None, etc="/etc", repair=False):
    """Compare external IPTV references; write bouquets only on explicit repair."""
    logger = logger or (lambda _: None)
    snapshots, records, reserved, signature = scan(etc)
    errors = []
    def mapping_log(message):
        if "failed" in message.lower():
            errors.append(message)
        logger(message)
    mapper = PrivateEpgApiClient(str(Path(etc) / "AzmanPanel" / "epg_access.json"), logger=mapping_log)
    names = sorted({r["name"] for r in records})
    candidates = {name: [name] + ([] if name.lower().endswith(".pl") else [name + ".pl"]) for name in names}
    matches = mapper.resolve([item for values in candidates.values() for item in values]) if names else {}
    counts = dict(correct=0, change=0, missing=0, ambiguous=0, unavailable=0)
    lines, assignments, compatible = [], [], set()
    for record in records:
        references = {"1:" + matches[value] for value in candidates[record["name"]]
                      if valid_reference(matches.get(value))}
        target = next(iter(references)) if len(references) == 1 else None
        state = ("unavailable" if errors else "ambiguous" if len(references) > 1 else
                 "missing" if not target else "correct" if target.upper() == record["reference"].upper() else "change")
        counts[state] += 1
        if state == "correct":
            compatible.add(record["reference"])
        label = {"correct": "OK", "change": "DO ZMIANY", "missing": "BRAK MAPOWANIA",
                 "ambiguous": "NIEJEDNOZNACZNE", "unavailable": "BŁĄD API"}[state]
        name = record["name"].replace("\n", " ").replace("\r", " ")
        lines.append("[%s] %s | %s:%d" % (label, name, record["file"], record["line"] + 1))
        if state == "change":
            lines.extend(["  Obecna: " + record["reference"], "  Azman:  " + target])
            assignments.append(dict(record, source=target, target=target))
    changed = 0
    if repair and assignments and not errors:
        applied, changed = update_bouquets(etc, snapshots, assignments)
        lines.insert(0, "Poprawiono bukiety: %d. Pominięto kanały zmienione podczas analizy: %d." %
                     (changed, len(assignments) - len(applied)))
        if changed:
            def reload():
                from enigma import eDVBDB
                eDVBDB.getInstance().reloadBouquets()
            call_in_main_thread(reload, logger=logger)
            compatible.update(record["target"] for record in applied)
    header = ("Audyt IPTV — mapowanie Azman/Kamoz\n"
              "Kanały: %d | OK: %d | Do zmiany: %d | Brak: %d | Niejednoznaczne: %d | Błąd API: %d\n"
              "Zgodna referencja pozwala przypisać EPG; dostępność ramówki zależy od źródła.\n\n") % (
                  len(records), counts["correct"], counts["change"], counts["missing"], counts["ambiguous"], counts["unavailable"])
    report = header + "\n".join(lines)
    BackupStore._write(Path(REPORT_FILE), report.encode("utf-8"))
    # Only canonical references receive data. Auditing never repairs implicitly.
    config = epg_events._config() if compatible else {}
    pending = {}
    references = sorted(compatible)
    for offset in range(0, len(references), epg_events.MAX_CHANNELS_PER_REQUEST):
        batch = references[offset:offset + epg_events.MAX_CHANNELS_PER_REQUEST]
        events = epg_events._request_events(config.get("url", ""), config, batch, logger)
        for reference, raw in (events or {}).items():
            if reference in compatible:
                tuples = epg_events._to_event_tuples(raw)
                if tuples:
                    pending[reference] = tuples
    if pending:
        def inject():
            from enigma import eEPGCache
            cache = eEPGCache.getInstance()
            for reference, events in pending.items():
                try:
                    cache.importEvents(reference, events)
                except Exception as error:
                    logger("IPTV EPG import failed: " + type(error).__name__)
        call_in_main_thread(inject, logger=logger)
    logger("IPTV audit: channels=%d changed_bouquets=%d" % (len(records), changed))
    return report


def audit_external_async(logger=None, repair=False):
    queue = _repair_queue if repair else _queue
    return queue.submit(lambda logger=None, pattern=None: audit_external(logger=logger, repair=repair), logger=logger)
