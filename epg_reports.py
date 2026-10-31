"""Merge independent EPG scopes while retaining the legacy report views."""
import json
import os
import threading
import time

from .private_storage import atomic_json

_LOCK = threading.RLock()
MAX_REPORT_BYTES = 4 * 1024 * 1024
TTL_SECONDS = 86400


def read_state(path):
    try:
        with open(path, 'rb') as handle:
            raw = handle.read(MAX_REPORT_BYTES + 1)
        if len(raw) > MAX_REPORT_BYTES:
            raise ValueError('EPG report too large')
        return json.loads(raw)
    except FileNotFoundError:
        return None


def merge_report(path, scope_updates, kind, active_scopes=None, drop_scopes=()):
    """None preserves an uncertain entry; an empty value clears a known one.

    Each scope update covers its complete current channel set. Scopes absent
    from a partial job are untouched. A full job can discard removed bouquets.
    """
    with _LOCK:
        state_path = path + '.scopes.json'
        state = read_state(state_path)
        if state is None:
            state = {'schema': 1, 'scopes': {}}
            legacy = read_state(path)
            if isinstance(legacy, list) and legacy:
                state['scopes']['__legacy__'] = {'updated_at': int(time.time()),
                    'entries': {str(i): item for i, item in enumerate(legacy)}}
        if not isinstance(state, dict) or state.get('schema') != 1 or not isinstance(state.get('scopes'), dict):
            raise ValueError('Invalid EPG report state')
        scopes = state['scopes']
        now = int(time.time())
        for scope in list(scopes):
            if (now - int(scopes[scope].get('updated_at') or 0) >= TTL_SECONDS
                    or scope in drop_scopes or (active_scopes is not None and scope not in active_scopes)):
                del scopes[scope]
        for scope, updates in scope_updates.items():
            previous = scopes.get(scope, {}).get('entries', {})
            entries = {}
            for key, value in updates.items():
                if value is None:
                    if key in previous:
                        entries[key] = previous[key]
                elif value:
                    entries[key] = value
            scopes[scope] = {'updated_at': now, 'entries': entries}
        if kind == 'events':
            names = set()
            for group in scopes.values():
                for value in group['entries'].values():
                    names.update([value] if isinstance(value, str) else value)
            view = sorted(names)
        else:
            by_name = {}
            for group in scopes.values():
                for value in group['entries'].values():
                    if isinstance(value, dict) and value.get('name'):
                        by_name[value['name']] = value
            view = sorted(by_name.values(), key=lambda item: item['name'])
        if any(len(json.dumps(value, ensure_ascii=False).encode('utf-8')) > MAX_REPORT_BYTES
               for value in (state, view)):
            raise ValueError('Merged EPG report too large')
        atomic_json(state_path, state)
        if view:
            atomic_json(path, view)
        else:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        return view


def discard_scope(path, scope, kind):
    with _LOCK:
        # Without the sidecar, old reports cannot reliably be attributed.
        # Preserve them until migration or expiry rather than guessing.
        if os.path.exists(path + '.scopes.json'):
            merge_report(path, {}, kind, drop_scopes={scope})
        if kind == 'events':
            status_path = path.replace('missing_events', 'status')
            status = read_state(status_path)
            if isinstance(status, dict) and isinstance(status.get('scopes'), dict):
                status['scopes'].pop(scope, None)
                atomic_json(status_path, status)
