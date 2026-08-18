"""Prywatny mapper EPG dla bukietów Azman Panel."""

import json
import os
import re
import time

from .epg_private import PrivateEpgApiClient
from . import utils


class PanelEpgMapper(object):
    ACCESS_FILE = "/etc/AzmanPanel/epg_access.json"
    REPORT_FILE = "/tmp/epg_missing_mappings.json"
    REPORT_TTL_SECONDS = 86400

    def __init__(self):
        self.missing = {}
        self._remove_expired_report()
        self.private_api = PrivateEpgApiClient(
            self.ACCESS_FILE,
            logger=lambda message: utils.log_event("EPG mapper: %s" % message),
        )

    @staticmethod
    def normalize(value):
        import unicodedata
        text = unicodedata.normalize("NFKD", str(value or "").lower())
        text = text.encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"\[[^\]]*\]|\([^\)]*\)", " ", text)
        return re.sub(r"[^a-z0-9]+", "", text)

    def available(self):
        return self.private_api.enabled()

    def prefetch(self, names):
        candidates = []
        for name in names or []:
            text = str(name or "").strip()
            if not text:
                continue
            candidates.append(text)
            if not text.lower().endswith(".pl"):
                candidates.append(text + ".pl")
            candidates.extend(("Polskie Radio " + text, "PolskieRadio" + text))
        self.private_api.resolve(candidates)
        if candidates and not self.available():
            utils.log_event("EPG mapper: private mapping disabled or access configuration unavailable")

    def reference(self, name):
        text = str(name or "").strip()
        candidates = [text]
        if text and not text.lower().endswith(".pl"):
            candidates.append(text + ".pl")
        candidates.extend(("Polskie Radio " + text, "PolskieRadio" + text))
        matches = self.private_api.resolve(candidates)
        for candidate in candidates:
            reference = matches.get(candidate, "")
            if reference:
                return reference
        self.missing[self.normalize(text)] = {"name": text, "last_seen": int(time.time())}
        self._save_report()
        return ""

    def _save_report(self):
        try:
            parent = os.path.dirname(self.REPORT_FILE)
            if not os.path.isdir(parent):
                os.makedirs(parent)
            temporary = self.REPORT_FILE + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(list(self.missing.values()), handle, ensure_ascii=False, indent=2)
            os.replace(temporary, self.REPORT_FILE)
        except Exception:
            pass

    def _remove_expired_report(self):
        try:
            if not os.path.isfile(self.REPORT_FILE):
                return
            age = time.time() - os.path.getmtime(self.REPORT_FILE)
            if age >= self.REPORT_TTL_SECONDS:
                os.unlink(self.REPORT_FILE)
        except Exception:
            pass
