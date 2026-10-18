"""Bounded, local backups. No arbitrary archive extraction or remote upload."""

import base64
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from datetime import datetime, timezone

KEEP = 3
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 24 * 1024 * 1024
MAX_ARCHIVE = 34 * 1024 * 1024
PREFIXES = ("config.plugins.AzmanPanel.", "config.plugins.azmanfreetvplayer.")
BOUQUET = re.compile(r"^userbouquet\.(?:azmanpanel_|azmanfreetvplayer_|azman_iptv_|azmanplayer_)[A-Za-z0-9_.-]+\.(?:tv|radio)$")
ANY_BOUQUET = re.compile(r"^userbouquet\.[A-Za-z0-9_.-]+\.(?:tv|radio)$")


class BackupStore:
    def __init__(self, etc="/etc"):
        self.etc = Path(etc)
        self.directory = self.etc / "AzmanPanel" / "backups"

    def _directory(self):
        for path in (self.etc / "AzmanPanel", self.directory):
            if path.is_symlink():
                raise ValueError("Niedozwolony odnośnik w katalogu kopii")
            path.mkdir(mode=0o700, exist_ok=True)
            os.chmod(str(path), 0o700)

    def _allowed(self, name):
        parts = name.split("/")
        if len(parts) != 2 or any(p in ("", ".", "..") for p in parts):
            return False
        directory, filename = parts
        if directory in ("AzmanPanel", "AzmanFreeTVPlayer"):
            return bool(re.fullmatch(r"[A-Za-z0-9_.-]+\.json", filename))
        return directory == "enigma2" and (filename == "settings" or filename in ("bouquets.tv", "bouquets.radio") or bool(ANY_BOUQUET.fullmatch(filename)))

    def _path(self, name):
        if not self._allowed(name):
            raise ValueError("Niedozwolona ścieżka w kopii")
        target = self.etc / name
        if target.parent.is_symlink() or target.is_symlink():
            raise ValueError("Niedozwolony odnośnik w konfiguracji")
        return target

    @staticmethod
    def _read(path, limit=MAX_FILE):
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ValueError("Oczekiwano zwykłego pliku")
            data = handle.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Przekroczono limit rozmiaru kopii")
        return data

    @staticmethod
    def _write(path, data):
        if path.parent.is_symlink() or path.is_symlink():
            raise ValueError("Niedozwolony odnośnik")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".azman-backup-", dir=str(path.parent))
        try:
            os.chmod(temporary, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, str(path))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _own_registration(line):
        names = re.findall(r'FROM BOUQUET "([^"]+)"', line)
        return line.startswith("#SERVICE ") and bool(names) and all(BOUQUET.fullmatch(name) for name in names)

    def create(self, extra_bouquets=()):
        self._directory()
        files = {}
        total = 0
        candidates = []
        for folder in ("AzmanPanel", "AzmanFreeTVPlayer", "enigma2"):
            parent = self.etc / folder
            if parent.is_symlink():
                raise ValueError("Niedozwolony odnośnik w konfiguracji")
            if parent.is_dir():
                candidates.extend(parent.iterdir())
        for path in sorted(candidates):
            name = path.relative_to(self.etc).as_posix()
            if path.parent.name == "enigma2" and ANY_BOUQUET.fullmatch(path.name) and not BOUQUET.fullmatch(path.name) and path.name not in extra_bouquets:
                continue
            if not self._allowed(name):
                continue
            data = self._read(self._path(name))
            if name == "enigma2/settings":
                data = b"".join(line for line in data.splitlines(keepends=True) if line.startswith(tuple(p.encode() for p in PREFIXES)))
            elif name in ("enigma2/bouquets.tv", "enigma2/bouquets.radio"):
                data = "".join(line for line in data.decode("utf-8").splitlines(keepends=True) if self._own_registration(line)).encode("utf-8")
            total += len(data)
            if total > MAX_TOTAL:
                raise ValueError("Konfiguracja przekracza limit 24 MiB")
            files[name] = base64.b64encode(data).decode("ascii")
        data = json.dumps({"schema": 1, "created": datetime.now(timezone.utc).isoformat(), "files": files}).encode("utf-8")
        if len(data) > MAX_ARCHIVE:
            raise ValueError("Kopia przekracza limit rozmiaru")
        name = "backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
        self._write(self.directory / name, data)
        for old in self.list()[KEEP:]:
            (self.directory / old).unlink()
        return name

    def list(self):
        self._directory()
        return sorted((p.name for p in self.directory.iterdir() if re.fullmatch(r"backup-\d{8}T\d{12}Z\.json", p.name) and p.is_file() and not p.is_symlink()), reverse=True)

    def restore(self, name):
        if name not in self.list():
            raise ValueError("Nie znaleziono kopii")
        snapshot = json.loads(self._read(self.directory / name, MAX_ARCHIVE).decode("utf-8"))
        if snapshot.get("schema") != 1 or not isinstance(snapshot.get("files"), dict):
            raise ValueError("Niepoprawny format kopii")
        files = {}
        total = 0
        # Validate the entire snapshot before changing any destination.
        for filename, encoded in snapshot["files"].items():
            self._path(filename)
            data = base64.b64decode(encoded, validate=True)
            total += len(data)
            if len(data) > MAX_FILE or total > MAX_TOTAL:
                raise ValueError("Przekroczono limit rozmiaru kopii")
            if filename == "enigma2/settings" and any(not line.startswith(tuple(p.encode() for p in PREFIXES)) for line in data.splitlines()):
                raise ValueError("Kopia zawiera obce ustawienia")
            if filename in ("enigma2/bouquets.tv", "enigma2/bouquets.radio") and any(not self._own_registration(line) for line in data.decode("utf-8").splitlines()):
                raise ValueError("Kopia zawiera obce rejestracje")
            files[filename] = data
        safety_copy = self.create(extra_bouquets={name.split("/")[1] for name in files if name.startswith("enigma2/userbouquet.")})
        for filename, data in files.items():
            path = self._path(filename)
            if filename == "enigma2/settings":
                current = self._read(path) if path.exists() else b""
                preserved = [line for line in current.splitlines() if not line.startswith(tuple(p.encode() for p in PREFIXES))]
                data = b"\n".join(preserved + data.splitlines()) + b"\n"
            elif filename in ("enigma2/bouquets.tv", "enigma2/bouquets.radio"):
                current = self._read(path).decode("utf-8") if path.exists() else "#NAME Bouquets\n"
                preserved = [line for line in current.splitlines() if not self._own_registration(line)]
                data = ("\n".join(preserved + data.decode("utf-8").splitlines()) + "\n").encode("utf-8")
            self._write(path, data)
        return safety_copy


def main():
    import fcntl
    store = BackupStore()
    store._directory()
    fd = os.open(str(store.directory / ".lock"), os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if len(sys.argv) == 2 and sys.argv[1] == "create":
            print("Utworzono kopię: " + store.create())
        elif len(sys.argv) == 3 and sys.argv[1] == "restore":
            print("Przywrócono ustawienia. Kopia stanu sprzed przywracania: " + store.restore(sys.argv[2]))
        else:
            return 1
        return 0
    except Exception as error:
        print("Operacja kopii nie powiodła się: " + type(error).__name__)
        return 1
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
