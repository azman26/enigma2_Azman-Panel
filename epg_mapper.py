# -*- coding: utf-8 -*-
"""Lekki mapper EPG wspolny dla bukietow radiowych Azman Panel."""

import json
import lzma
import os
import re
import urllib.request
import time


class PanelEpgMapper(object):
    SOURCE_URL = "https://kamoz.pl/kamoz.channels.xml.xz"
    CACHE_FILE = "/tmp/.azmanpanel/kamoz.channels.xml"
    REPORT_FILE = "/tmp/.azmanpanel/epg_missing.json"
    CHANNEL_PATTERN = re.compile(
        r'<channel\s+id="([^"]+)"[^>]*>\s*([^<]+?)\s*</channel>\s*'
        r'<!--\s*(.*?)\s*-->', re.DOTALL
    )

    def __init__(self):
        self.by_name = {}
        self.missing = {}

    @staticmethod
    def normalize(value):
        import unicodedata
        text = unicodedata.normalize("NFKD", str(value or "").lower())
        text = text.encode("ascii", "ignore").decode("ascii")
        text = re.sub(r"\[[^\]]*\]|\([^\)]*\)", " ", text)
        text = re.sub(r"\b(?:uhd|fhd|hd|sd|4k)\b", " ", text)
        return re.sub(r"[^a-z0-9]+", "", text)

    def load(self):
        try:
            if not os.path.isfile(self.CACHE_FILE) or os.path.getsize(self.CACHE_FILE) == 0:
                parent = os.path.dirname(self.CACHE_FILE)
                if not os.path.isdir(parent):
                    os.makedirs(parent)
                with urllib.request.urlopen(self.SOURCE_URL, timeout=20) as response:
                    xml_data = lzma.decompress(response.read())
                temporary = self.CACHE_FILE + ".tmp"
                with open(temporary, "wb") as handle:
                    handle.write(xml_data)
                os.replace(temporary, self.CACHE_FILE)
            with open(self.CACHE_FILE, "rb") as handle:
                xml_text = handle.read().decode("utf-8", "replace")
            for match in self.CHANNEL_PATTERN.finditer(xml_text):
                reference = ":".join(str(match.group(2)).split(":")[1:10])
                if len(reference.split(":")) != 9:
                    continue
                for alias in str(match.group(3) or "").split(", "):
                    key = self.normalize(alias)
                    if key and key not in self.by_name:
                        self.by_name[key] = reference
            return bool(self.by_name)
        except Exception:
            return False

    def reference(self, name):
        if not self.by_name:
            self.load()
        text = str(name or "").strip()
        candidates = [text]
        if text and not text.lower().endswith(".pl"):
            candidates.append(text + ".pl")
        candidates.extend(("Polskie Radio " + text, "PolskieRadio" + text))
        reference = ""
        for candidate in candidates:
            reference = self.by_name.get(self.normalize(candidate), "")
            if reference:
                break
        if not reference:
            key = self.normalize(name)
            self.missing[key] = {"name": str(name), "last_seen": int(time.time())}
            self._save_report()
        return reference

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
