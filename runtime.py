"""Runtime information used to select compatible Azman packages."""

import platform
import sys


def _read_first_line(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return handle.readline().strip()
    except (OSError, IOError):
        return ""


def get_runtime_info():
    """Return image-independent compatibility information for the box."""
    version = sys.version_info
    return {
        "python": "%d.%d" % (version[0], version[1]),
        "python_major": version[0],
        "python_minor": version[1],
        "machine": platform.machine().lower(),
        "image": _read_first_line("/etc/image-version"),
        "openatv": _read_first_line("/etc/openatv-version"),
        "build": _read_first_line("/etc/build"),
    }


def package_runtime_tags(info=None):
    """Return stable manifest tags, with Python as the primary selector."""
    info = info or get_runtime_info()
    tags = ["py%s%s" % (info["python_major"], info["python_minor"])]
    machine = info.get("machine", "")
    if machine:
        tags.append(machine)
    tags.append("all")
    return tags
