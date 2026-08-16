"""Prywatny mapper EPG dla bukietów Azman Panel."""

import json
import os
import re
import time

from .epg_private import PrivateEpgApiClient


class PanelEpgMapper(object):
    ACCESS_FILE = "/etc/AzmanPanel/epg_access.json"
    REPORT_FILE = "/tmp/.azmanpanel/epg_missing.json"

    def __init__(self):
        self.missing = {}
        self.private_api = PrivateEpgApiClient(self.ACCESS_FILE)

    @staticmethod
    def normalize(value):
        import unicodedata
        text = unicodedata.normalize("NFKD", str(value or "").lower())
        text = text.encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"\[[^\]]*\]|\([^\)]*\)", " ", text)
        return re.sub(r"[^a-z0-9]+", "", text)

    def available(self):
        return self.private_api.enabled()

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
            with open(temporary, "w") as handle:
                json.dump(list(self.missing.values()), handle, ensure_ascii=False, indent=2)
            os.replace(temporary, self.REPORT_FILE)
        except Exception:
            pass
