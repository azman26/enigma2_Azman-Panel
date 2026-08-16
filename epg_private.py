from __future__ import print_function

import json
import os

try:
    from urllib.request import Request, urlopen
except ImportError:
    from urllib2 import Request, urlopen


class PrivateEpgApiClient(object):
    def __init__(self, config_file, logger=None):
        self.config_file = config_file
        self.logger = logger
        self.cache = {}

    def _log(self, message):
        try:
            if callable(self.logger):
                self.logger(message)
        except Exception:
            pass

    def _config(self):
        try:
            with open(self.config_file, "r") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def enabled(self):
        data = self._config()
        return bool(
            data.get("enabled") is True
            and str(data.get("url") or "").startswith("https://")
            and str(data.get("token") or "").strip()
            and str(data.get("box_id") or "").strip()
        )

    def resolve(self, names):
        names = [str(name or "").strip() for name in names or []]
        names = [name for index, name in enumerate(names) if name and name not in names[:index]]
        if not names or not self.enabled():
            return {}
        requested = [name for name in names if name not in self.cache]
        if requested:
            self._request(requested)
        return {name: self.cache.get(name, "") for name in names if self.cache.get(name)}

    def _request(self, names):
        config = self._config()
        payload = json.dumps({
            "box_id": str(config.get("box_id") or "").strip(),
            "channels": names,
        }).encode("utf-8")
        headers = {
            "Authorization": "Bearer %s" % str(config.get("token") or "").strip(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Cache-Control": "no-store",
            "User-Agent": "AzmanPanel-EPG/1",
        }
        try:
            request = Request(str(config.get("url")), data=payload, headers=headers)
            response = urlopen(request, timeout=int(config.get("timeout") or 12))
            try:
                result = json.loads(response.read().decode("utf-8"))
            finally:
                response.close()
            mappings = result.get("mappings") if isinstance(result, dict) else {}
            if not isinstance(mappings, dict):
                mappings = {}
            for name in names:
                reference = str(mappings.get(name) or "").strip()
                self.cache[name] = reference if len(reference.split(":")) == 9 else ""
        except Exception as error:
            self._log("private EPG API failed: %s" % error)
            for name in names:
                self.cache[name] = ""
