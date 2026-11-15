"""Coalesce each plugin's requests and serialize EPG fetches across Azman plugins."""
import sys
import threading
import types

_shared = sys.modules.setdefault("_azman_epg_jobs", types.ModuleType("_azman_epg_jobs"))
_global_lock = _shared.__dict__.setdefault("fetch_lock", threading.Lock())


class ImportQueue:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread = None
        self.pending = set()
        self.full = False
        self.callbacks = {}
        self.full_callback = None

    def submit(self, callback, logger=None, pattern=None):
        with self.lock:
            if pattern is None:
                self.full = True
                self.pending.clear()
                self.callbacks.clear()
                self.full_callback = (callback, logger)
            elif not self.full:
                self.pending.add(pattern)
                self.callbacks[pattern] = (callback, logger)
            if self.thread is not None:
                return self.thread

            def run():
                while True:
                    with self.lock:
                        if self.full:
                            patterns = [(None, self.full_callback)]
                        else:
                            patterns = [(item, self.callbacks[item]) for item in sorted(self.pending)]
                        self.full = False
                        self.pending.clear()
                        self.callbacks.clear()
                        self.full_callback = None
                        if not patterns:
                            self.thread = None
                            return
                    for item, (job_callback, job_logger) in patterns:
                        try:
                            with _global_lock:
                                job_callback(logger=job_logger, pattern=item)
                        except Exception as error:
                            if job_logger:
                                try:
                                    job_logger("EPG import failed: %s" % type(error).__name__)
                                except Exception:
                                    pass

            self.thread = threading.Thread(target=run, name="AzmanEpgImport")
            self.thread.daemon = True
            try:
                self.thread.start()
            except Exception:
                self.thread = None
                raise
            return self.thread


shared_import_queue = _shared.__dict__.setdefault('combined_queue_v1', ImportQueue())
