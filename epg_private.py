from __future__ import print_function

import json
import os
import time
import uuid

try:
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import Request, urlopen, HTTPError


# Samoobslugowa rejestracja (2026-09-21): kazdy box sam dostaje wlasny token
# przy pierwszym uzyciu, bez recznego wydawania przez wlasciciela - patrz
# private-server/register-epg-client.php. REGISTER_APP_KEY musi byc identyczny
# jak APP_KEY w tym pliku PHP; to nie jest sekret kryptograficzny (jest w
# publicznie dystrybuowanym kodzie pluginu), tylko filtr odstraszajacy
# przypadkowy ruch botow/skanerow do publicznego endpointu.
REGISTER_URL = "https://www.topolowa4.pl/api/register-epg-client.php"
REGISTER_APP_KEY = "azman-epg-client-2026"
EPG_MAP_URL = "https://www.topolowa4.pl/api/epg-map.php"
REGISTER_RETRY_SECONDS = 3600


class PrivateEpgApiClient(object):
    MAX_CHANNELS_PER_REQUEST = 150

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
            try:
                os.chmod(self.config_file, 0o600)
            except Exception:
                pass
            with open(self.config_file, "r") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_config(self, data):
        try:
            directory = os.path.dirname(self.config_file)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)
            temporary = self.config_file + ".tmp"
            with open(temporary, "w") as handle:
                json.dump(data, handle)
            os.chmod(temporary, 0o600)
            replace = getattr(os, "replace", os.rename)
            replace(temporary, self.config_file)
        except Exception as error:
            self._log("private EPG: cannot save config: %s" % error)

    def enabled(self):
        data = self._config()
        return bool(
            data.get("enabled") is True
            and str(data.get("url") or "").startswith("https://")
            and str(data.get("token") or "").strip()
            and str(data.get("box_id") or "").strip()
        )

    def _ensure_registered(self):
        """Jesli config nie ma jeszcze wazneg tokenu, rejestruje ten box
        samoobslugowo w register-epg-client.php i zapisuje wynik do
        config_file. Bez tego uzytkownik musialby recznie prosic wlasciciela
        o token - przy ~200+ instalacjach nie do utrzymania."""
        data = self._config()
        if self.enabled():
            return
        last_attempt = float(data.get("_register_attempted_at") or 0)
        if time.time() - last_attempt < REGISTER_RETRY_SECONDS:
            return  # nie bijemy serwera przy kazdym wywolaniu po nieudanej probie
        box_id = str(data.get("box_id") or "").strip()
        if not box_id:
            box_id = uuid.uuid4().hex
            data["box_id"] = box_id
            self._save_config(data)
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
                "enabled": True,
                "url": EPG_MAP_URL,
                "token": token,
                "box_id": box_id,
                "timeout": 12,
            })
            data.pop("_register_attempted_at", None)
            self._save_config(data)
            self._log("private EPG: self-registration succeeded box_id=%s" % box_id)
        except Exception as error:
            data["_register_attempted_at"] = time.time()
            self._save_config(data)
            self._log("private EPG: self-registration failed: %s" % self._describe_error(error))

    def _invalidate_and_retry_registration(self):
        """Serwer odrzucil token (403 - wygasl albo zostal uniewazniony) -
        czyscimy go, zeby nastepne wywolanie _ensure_registered od razu
        probowalo zarejestrowac sie ponownie zamiast czekac na retry-cooldown."""
        data = self._config()
        data["enabled"] = False
        data.pop("token", None)
        data.pop("_register_attempted_at", None)
        self._save_config(data)

    def resolve(self, names):
        names = [str(name or "").strip() for name in names or []]
        names = [name for index, name in enumerate(names) if name and name not in names[:index]]
        if not names:
            return {}
        self._ensure_registered()
        if not self.enabled():
            return {}
        requested = [name for name in names if name not in self.cache]
        if requested:
            for offset in range(0, len(requested), self.MAX_CHANNELS_PER_REQUEST):
                self._request(requested[offset:offset + self.MAX_CHANNELS_PER_REQUEST])
        return {name: self.cache.get(name, "") for name in names if self.cache.get(name)}

    @staticmethod
    def _describe_error(error):
        # Bez tego log pokazywal tylko "HTTPError" bez kodu statusu (403/404/
        # 429/503...), wiec kazda awaria wygladala identycznie i trzeba bylo
        # recznie odpytywac API, zeby ustalic prawdziwa przyczyne.
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
            resolved_count = sum(1 for name in names if self.cache.get(name))
            self._log("private EPG API resolved %d of %d references" % (resolved_count, len(names)))
        except HTTPError as error:
            if error.code == 403:
                self._invalidate_and_retry_registration()
            self._log("private EPG API failed: %s" % self._describe_error(error))
            for name in names:
                self.cache[name] = ""
        except Exception as error:
            self._log("private EPG API failed: %s" % self._describe_error(error))
            for name in names:
                self.cache[name] = ""
