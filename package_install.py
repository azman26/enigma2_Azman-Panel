"""Run opkg without removing the working package before an upgrade."""

import os
import subprocess
import sys
from .runtime import panel_tool_argv


def install_package(package_path, runner=None):
    runner = runner or subprocess.call
    package_path = os.path.abspath(package_path)
    if not os.path.isfile(package_path):
        print("Brak pobranego pakietu IPK.", flush=True)
        return 1
    print("Sprawdzanie planu instalacji i zależności...", flush=True)
    result = runner(["opkg", "--noaction", "--force-reinstall", "install", package_path])
    if result:
        print("Sprawdzenie nie powiodło się. Panel nie usunął poprzedniego pakietu. "
              "Przy konflikcie wariantów potrzebna jest osobna migracja.", flush=True)
        return result
    print("Tworzenie lokalnej kopii ustawień przed aktualizacją...", flush=True)
    result = runner(panel_tool_argv("backups", "create", python=sys.executable))
    if result:
        print("Nie udało się utworzyć kopii. Instalacja została zatrzymana.", flush=True)
        return result
    print("Instalowanie zweryfikowanego pakietu...", flush=True)
    return runner(["opkg", "--force-reinstall", "install", package_path])


def main():
    # Serialize installs started by Panel; opkg also protects its own database.
    import fcntl
    import tempfile
    lock_path = os.path.join(tempfile.gettempdir(), ".azmanpanel-install.lock")
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Inna instalacja Azman Panel jest już uruchomiona.", flush=True)
            return 1
        if len(sys.argv) != 2:
            return 1
        return install_package(sys.argv[1])
    except OSError as error:
        print("Nie udało się uruchomić instalacji: %s" % type(error).__name__, flush=True)
        return 1
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    sys.exit(main())
