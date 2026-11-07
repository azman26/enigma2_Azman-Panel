# -*- coding: utf-8 -*-
"""Wspólny dostęp do prywatnego API EPG: konfiguracja, samoobsługowa
rejestracja boxa i opis błędów. Używane przez epg_mapper.py (referencje DVB
przy zapisie bukietu) i epg_events.py (import eventów) - wcześniej każdy z nich
miał własną kopię tej logiki."""
from __future__ import print_function

from .epg_validation import read_json
from .private_storage import atomic_json
import json
import os
import threading
import sys
import types
import time
import uuid
from contextlib import contextmanager

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    from urllib.request import Request, urlopen
except ImportError:
    from urllib2 import Request, urlopen


from .epg_http_transport import private_urlopen as urlopen

# Samoobslugowa rejestracja (2026-09-21): kazdy box sam dostaje wlasny token
# przy pierwszym uzyciu, bez recznego wydawania przez wlasciciela - patrz
# private-server/register-epg-client.php. REGISTER_APP_KEY musi byc identyczny
# jak APP_KEY w tym pliku PHP; to nie jest sekret kryptograficzny (jest w
# publicznie dystrybuowanym kodzie pluginu), tylko filtr odstraszajacy
# przypadkowy ruch botow/skanerow do publicznego endpointu. Ten sam plik
# ACCESS_FILE co PanelEpgMapper (00 AzmanPanel/epg_private.py) - jesli
# uzytkownik ma oba pluginy, rejestracja odbywa sie tylko raz.
ACCESS_FILE = "/etc/AzmanPanel/epg_access.json"
REGISTER_URL = "https://www.topolowa4.pl/api/register-epg-client.php"
REGISTER_APP_KEY = "azman-epg-client-2026"
EPG_MAP_URL = "https://www.topolowa4.pl/api/epg-map.php"
REGISTER_RETRY_SECONDS = 3600
# Wspolna blokada z Azman Panel (ta sama nazwa pliku w jego epg_events.py i
# epg_private.py). Oba pluginy rejestruja sie przy starcie Enigmy2 - bez niej
# kazdy potrafil wygenerowac wlasny box_id i zarejestrowac sie osobno.
LOCK_FILE = ACCESS_FILE + ".lock"
_shared_access = sys.modules.setdefault("_azman_epg_access", types.ModuleType("_azman_epg_access"))
_THREAD_LOCK = _shared_access.__dict__.setdefault("registration_lock", threading.RLock())


def load_config():
    try:
        try:
            os.chmod(ACCESS_FILE, 0o600)
        except Exception:
            pass
        with open(ACCESS_FILE, "r") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(data, logger=None):
    try:
        atomic_json(ACCESS_FILE, data)
        os.chmod(ACCESS_FILE, 0o600)
    except Exception as error:
        if logger:
            logger("cannot save access config: %s" % error)


def _configured(data):
    return bool(
        data.get("enabled") is True
        and str(data.get("url") or "").startswith("https://")
        and str(data.get("token") or "").strip()
        and str(data.get("box_id") or "").strip()
    )


def describe_error(error):
    # Bez tego log pokazywal tylko "HTTPError" bez kodu statusu (403/404/
    # 429/503...), wiec kazda awaria wygladala identycznie i trzeba bylo
    # recznie odpytywac API, zeby ustalic prawdziwa przyczyne.
    detail = error.__class__.__name__
    status = getattr(error, "code", None)
    if status:
        detail += " status=%s" % status
    return detail


@contextmanager
def registration_lock():
    """Blokada miedzy watkami i miedzy pluginami (flock). Gdy plik blokady
    nie da sie otworzyc, rejestracja idzie bez niej - jak dawniej."""
    with _THREAD_LOCK:
        handle = None
        try:
            directory = os.path.dirname(LOCK_FILE)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)
            handle = open(LOCK_FILE, "a+")
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except Exception:
            if handle is not None:
                handle.close()
            handle = None
        try:
            yield
        finally:
            if handle is not None:
                try:
                    if fcntl is not None:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    handle.close()


def ensure_registered(logger=None):
    """Jesli config nie ma jeszcze waznego tokenu, rejestruje ten box
    samoobslugowo w register-epg-client.php i zapisuje wynik do ACCESS_FILE.
    Bez tego uzytkownik musialby recznie prosic wlasciciela o token - przy
    ~200+ instalacjach nie do utrzymania."""
    logger = logger or (lambda _message: None)
    if _configured(load_config()):
        return
    with registration_lock():
        # Ponowny odczyt pod blokada - drugi plugin/watek mogl wlasnie
        # zakonczyc rejestracje.
        _ensure_registered_locked(logger)


def _ensure_registered_locked(logger):
    data = load_config()
    if _configured(data):
        return
    last_attempt = float(data.get("_register_attempted_at") or 0)
    if time.time() - last_attempt < REGISTER_RETRY_SECONDS:
        return  # nie bijemy serwera przy kazdym wywolaniu po nieudanej probie
    box_id = str(data.get("box_id") or "").strip()
    if not box_id:
        box_id = uuid.uuid4().hex
        data["box_id"] = box_id
        save_config(data, logger)
    try:
        payload = json.dumps({"box_id": box_id}).encode("utf-8")
        request = Request(REGISTER_URL, data=payload, headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Azman-App-Key": REGISTER_APP_KEY,
            "User-Agent": "AzmanFreeTV-EPGRegister/1",
        })
        response = urlopen(request, timeout=15)
        try:
            result = read_json(response)
        finally:
            response.close()
        token = str(result.get("token") or "").strip()
        if not token:
            raise ValueError("empty token in response")
        data.update({"enabled": True, "url": EPG_MAP_URL, "token": token, "box_id": box_id, "timeout": 12})
        data.pop("_register_attempted_at", None)
        save_config(data, logger)
        logger("self-registration succeeded box_id=%s" % box_id)
    except Exception as error:
        data["_register_attempted_at"] = time.time()
        save_config(data, logger)
        logger("self-registration failed: %s" % describe_error(error))


def invalidate_registration():
    """Serwer odrzucil token (403 - wygasl albo zostal uniewazniony) -
    czyscimy go, zeby nastepne wywolanie ensure_registered od razu probowalo
    zarejestrowac sie ponownie zamiast czekac na retry-cooldown."""
    data = load_config()
    data["enabled"] = False
    data.pop("token", None)
    data.pop("_register_attempted_at", None)
    save_config(data)


def available(logger=None):
    ensure_registered(logger)
    return _configured(load_config())
