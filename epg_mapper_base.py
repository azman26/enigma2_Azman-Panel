# -*- coding: utf-8 -*-
from __future__ import print_function

import json
import os
import re
import time
import sys
import types
import threading
from email.utils import parsedate_to_datetime

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import Request, urlopen, HTTPError

from . import epg_access
from .epg_validation import read_json, valid_reference
from .epg_reports import merge_report


from .epg_http_transport import private_urlopen as urlopen

from .epg_profile import EPG_EXCLUDED_PROVIDERS, REPORT_PREFIX

_RATE_STATE = sys.modules.setdefault('_azman_epg_mapping_rate', types.ModuleType('_azman_epg_mapping_rate'))
_RATE_LOCK = _RATE_STATE.__dict__.setdefault('lock', threading.RLock())


def _retry_delay(headers):
    value = str(headers.get('Retry-After', '') if headers else '').strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = parsedate_to_datetime(value).timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            seconds = 60
    return max(1, min(86400, seconds))

class FreeTvEpgMapper(object):
    REPORT_FILE = REPORT_PREFIX + "_missing_mappings.json"
    REPORT_TTL_SECONDS = 86400
    MAX_CHANNELS_PER_REQUEST = 150

    def __init__(self, logger=None, provider_id=None):
        self.logger = logger or (lambda _message: None)
        self.cache = {}
        self.failed = set()
        self.missing = {}
        self.provider_id = provider_id or '__legacy__'
        self.checked = {}
        self._remove_expired_report()

    def _log(self, message):
        try:
            self.logger("EPG mapper: %s" % message)
        except Exception:
            pass

    def _config(self):
        return epg_access.load_config()

    def available(self):
        return epg_access.available(self._log)

    @staticmethod
    def normalize(value):
        import unicodedata
        text = unicodedata.normalize("NFKD", str(value or "").lower())
        text = text.encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"\[[^\]]*\]|\([^\)]*\)", " ", text)
        return re.sub(r"[^a-z0-9]+", "", text)

    def _candidates(self, name):
        text = str(name or "").strip()
        if not text:
            return []
        values = [text]
        if not text.lower().endswith(".pl"):
            values.append(text + ".pl")
        return values

    def prefetch(self, names):
        # Resolve primary names first. Only unresolved channels need aliases;
        # asking for name + .pl unconditionally consumed the server budget twice.
        groups = [self._candidates(name) for name in names or []]
        for position in range(max((len(group) for group in groups), default=0)):
            requested = []
            for group in groups:
                if any(self.cache.get(candidate) for candidate in group):
                    continue
                if any(candidate in self.failed for candidate in group):
                    continue
                if position < len(group):
                    candidate = group[position]
                    if candidate not in self.cache and candidate not in requested:
                        requested.append(candidate)
            self._prefetch_candidates(requested)

    def _prefetch_candidates(self, names):
        requested = []
        for name in names or []:
            if name not in self.cache and name not in self.failed and name not in requested:
                requested.append(name)
        if not requested:
            return
        if not self.available():
            self.failed.update(requested)
            self._log("private mapping disabled or access configuration unavailable")
            return
        for offset in range(0, len(requested), self.MAX_CHANNELS_PER_REQUEST):
            self._request(requested[offset:offset + self.MAX_CHANNELS_PER_REQUEST])

    def reference(self, name):
        candidates = self._candidates(name)
        self.prefetch([name])
        key = self.normalize(name)
        for candidate in candidates:
            reference = self.cache.get(candidate, "")
            if reference:
                self.checked[key] = []
                return reference
        text = str(name or "").strip()
        if text and not self.lookup_failed(name):
            self.missing[key] = {"name": text, "last_seen": int(time.time())}
            self.checked[key] = self.missing[key]
        elif text:
            self.checked[key] = None
        return ""

    def lookup_failed(self, name):
        return any(candidate in self.failed for candidate in self._candidates(name))

    def _request(self, names):
        with _RATE_LOCK:
            remaining = int(getattr(_RATE_STATE, 'retry_at', 0) - time.time())
        if remaining > 0:
            self.failed.update(names)
            self._log('mapping deferred after HTTP 429; retry in %ds; existing references retained' % remaining)
            return
        config = self._config()
        payload = json.dumps({
            "box_id": str(config.get("box_id") or "").strip(),
            "provider": self.provider_id,
            "channels": names,
        }).encode("utf-8")
        headers = {
            "Authorization": "Bearer %s" % str(config.get("token") or "").strip(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Cache-Control": "no-store",
            "User-Agent": "AzmanFreeTV-EPG/1",
        }
        try:
            request = Request(str(config.get("url")), data=payload, headers=headers)
            response = urlopen(request, timeout=int(config.get("timeout") or 12))
            try:
                result = read_json(response)
            finally:
                response.close()
            mappings = result.get("mappings")
            # Legacy PHP encodes an empty associative array as [] instead of {}.
            if mappings == []:
                mappings = {}
            if not isinstance(mappings, dict):
                raise ValueError("Invalid EPG mappings")
            self.failed.difference_update(names)
            for name in names:
                reference = mappings.get(name) or ""
                if valid_reference(reference):
                    self.cache[name] = reference
                elif not reference:
                    self.cache[name] = ""
                else:
                    self.failed.add(name)
            self._log("private EPG API resolved %d of %d references" % (
                sum(1 for name in names if self.cache.get(name)), len(names)
            ))
        except HTTPError as error:
            if error.code == 429:
                delay = _retry_delay(error.headers)
                with _RATE_LOCK:
                    _RATE_STATE.retry_at = max(getattr(_RATE_STATE, 'retry_at', 0), time.time() + delay)
                self._log('server rate limit reached; mapping paused for %ds' % delay)
            if error.code == 403:
                epg_access.invalidate_registration()
            self._log("private EPG API failed: %s" % epg_access.describe_error(error))
            self.failed.update(names)
        except Exception as error:
            self._log("private EPG API failed: %s" % epg_access.describe_error(error))
            self.failed.update(names)

    def _save_report(self):
        try:
            merge_report(self.REPORT_FILE, {self.provider_id: self.checked}, 'mappings')
        except Exception as error:
            self._log("mapping report not saved: %s" % type(error).__name__)

    def save_report(self):
        self._save_report()

    def _remove_expired_report(self):
        try:
            if os.path.isfile(self.REPORT_FILE) and time.time() - os.path.getmtime(self.REPORT_FILE) >= self.REPORT_TTL_SECONDS:
                os.unlink(self.REPORT_FILE)
        except Exception:
            pass
