"""Write private state without truncating the previous successful save."""
import json
import os
import tempfile
import threading

_WRITE_LOCK = threading.RLock()


def atomic_json(path, value):
    with _WRITE_LOCK:
        return _atomic_json(path, value)


def _atomic_json(path, value):
    directory = os.path.dirname(path) or '.'
    os.makedirs(directory, mode=0o700, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.azman-state-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
