"""Local status report; never export profiles or authentication files."""

import platform
import json
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import constants
from .backups import BackupStore


def report():
    lines = ["Azman — diagnostyka", "UTC: " + datetime.now(timezone.utc).isoformat(),
             "Panel: " + constants.PLUGIN_VERSION, "Python: " + platform.python_version(),
             "Architektura: " + platform.machine()]
    try:
        result = subprocess.run(["opkg", "list-installed", "*azman*"], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=5, universal_newlines=True)
        for line in result.stdout[:32768].splitlines():
            if re.fullmatch(r"enigma2-plugin-[a-z0-9-]+ - [A-Za-z0-9.+:~_-]+", line):
                lines.append(line)
    except (OSError, subprocess.TimeoutExpired):
        lines.append("Lista pakietów: niedostępna")
    for label, ports in (("HLS", range(7092, 7095)), ("TS", range(7095, 7098))):
        opened = []
        for port in ports:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.15):
                    opened.append(str(port))
            except OSError:
                pass
        lines.append("Porty %s (%s): %s" % (label, ",".join(str(p) for p in ports), ",".join(opened) or "zamknięte"))
    lines.append("Otwarty port TCP nie potwierdza poprawnego odtwarzania ani tożsamości usługi.")
    for name in ("azmanpanel_epg_status.json", "azmanfreetv_epg_status.json", "azmanpanel_external_epg_status.json"):
        try:
            status = json.loads(BackupStore._read(Path("/tmp") / name, 8192).decode("utf-8"))
            lines.append("EPG " + name)
            for key in ("attempted_at", "last_success_at", "imported_channels", "imported_events", "failed_references", "missing_channels", "scanned_channels", "matched_channels", "unmatched_channels", "modified_bouquets", "mapping_failed"):
                if isinstance(status.get(key), int):
                    if key in ("attempted_at", "last_success_at"):
                        stamp = datetime.fromtimestamp(status[key], timezone.utc).isoformat() if 0 < status[key] < 2147483648 else "brak"
                        lines.append("  %s (UTC): %s" % (key, stamp))
                    else:
                        lines.append("  %s: %d" % (key, status[key]))
            source = status.get("source", {})
            if isinstance(source, dict):
                for key in ("generation", "updated_at"):
                    value = str(source.get(key) or "")
                    if re.fullmatch(r"[0-9A-Za-z:.+_-]{1,80}", value):
                        lines.append("  source_%s: %s" % (key, value))
        except (OSError, ValueError, TypeError):
            lines.append("EPG " + name + ": brak statusu")
    try:
        from Plugins.Extensions.AzmanFreeTvPlayer.private_logging import sanitize
    except ImportError:
        sanitize = None
    if sanitize is None:
        lines.append("Logi pominięte: brak modułu maskowania FTVP.")
    else:
        for name in ("Azman_Panel.log", "Azman_FreeTV_Player.log"):
            lines.append("Log: " + name)
            try:
                # Read a bounded tail without following links or special files.
                path = Path("/tmp") / name
                import os
                import stat
                fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
                with os.fdopen(fd, "rb") as handle:
                    if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                        raise OSError("Not a regular log")
                    handle.seek(max(0, os.fstat(handle.fileno()).st_size - 32768))
                    tail = handle.read(32768).decode("utf-8", "replace").splitlines()[-40:]
                lines.extend(sanitize(line) for line in tail)
            except OSError:
                lines.append("Log niedostępny")
    return "\n".join(lines) + "\n"


def main():
    try:
        store = BackupStore()
        store._directory()
        data = report()
        target = store.etc / "AzmanPanel" / "diagnostics.txt"
        store._write(target, data.encode("utf-8"))
        print(data)
        print("Raport lokalny: " + str(target))
        print("Maskowanie obejmuje typowe dane poufne; przejrzyj raport przed udostępnieniem.")
        return 0
    except Exception as error:
        print("Diagnostyka nie powiodła się: " + type(error).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
