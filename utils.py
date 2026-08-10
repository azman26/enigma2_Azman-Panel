


import os
import zipfile
import traceback
import datetime
import shutil
import re
import tempfile

LOG_FILE = "/tmp/azman_panel.log"
BOUQUET_FILENAME_RE = re.compile(r"^userbouquet\.[A-Za-z0-9._-]+\.tv$")

def validate_bouquet_filename(filename):
    """Zwraca bezpieczną nazwę bukietu albo zgłasza ValueError."""
    if not isinstance(filename, str) or not BOUQUET_FILENAME_RE.fullmatch(filename):
        raise ValueError(f"Nieprawidłowa nazwa bukietu: {filename!r}")
    return filename

def panel_bouquet_filename(filename):
    filename = validate_bouquet_filename(filename)
    name = filename[len("userbouquet."):-len(".tv")]
    for prefix in ("azmanpanel_", "azmanplayer_", "azman_iptv_", "iptv_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    if name == "iptv-org-pl":
        name = "iptvorg_pl"
    name = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "lista"
    return "userbouquet.azmanpanel_%s.tv" % name

def atomic_write_lines(path, lines, encoding="utf-8"):
    """Zapisuje plik przez plik tymczasowy, aby uniknąć pustej konfiguracji."""
    directory = os.path.dirname(path) or "."
    fd, temporary_path = tempfile.mkstemp(prefix=".azman-", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.writelines(lines)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise

def remove_bouquet_and_registration(directory, filename):
    path = os.path.join(directory, filename)
    if os.path.exists(path):
        os.remove(path)
    registry_path = os.path.join(directory, "bouquets.tv")
    if not os.path.exists(registry_path):
        return
    with open(registry_path, "r") as handle:
        lines = handle.readlines()
    marker = 'FROM BOUQUET "%s"' % filename
    retained = [line for line in lines if marker not in line]
    if len(retained) != len(lines):
        atomic_write_lines(registry_path, retained)

def log_error(exception, context_info="Unknown", **kwargs):
    
    try:
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"--- ERROR LOG ENTRY: {timestamp} ---\n")
            f.write(f"Context: {context_info}\n\n")

            f.write("--- Additional Info ---\n")
            if not kwargs:
                f.write("None provided.\n")
            else:
                for key, value in kwargs.items():
                    f.write(f"{key.capitalize()}: {value}\n")
            f.write("\n")

            f.write("--- Exception Details ---\n")
            f.write(f"Type: {type(exception).__name__}\n")
            f.write(f"Message: {str(exception)}\n\n")

            f.write("--- Full Traceback ---\n")
            traceback.print_exc(file=f)
            f.write("\n")

            f.write("--- END OF ENTRY ---\n\n")

        print(f"[AzmanPanel] Error details have been written to: {LOG_FILE}")

    except Exception as log_e:
        print(f"[AzmanPanel] CRITICAL LOGGING ERROR: Could not write to log file {LOG_FILE}. Reason: {log_e}")


def safe_extract_zip_member(zip_ref, member, target_dir):
    """
    Bezpiecznie wypakowuje pojedynczy element z archiwum ZIP,
    zapobiegając atakom 'path traversal' i spłaszczając strukturę katalogów.
    """
    
    
    
    path_parts = member.filename.split('/')
    
    
    if len(path_parts) > 1:
        
        if not path_parts[-1]:
            return
        filename = os.path.join(*path_parts[1:])
    else:
        filename = member.filename

    target_path = os.path.join(target_dir, filename)
    
    
    
    
    target_root = os.path.realpath(target_dir)
    target_real = os.path.realpath(target_path)
    try:
        inside_target = os.path.commonpath((target_root, target_real)) == target_root
    except ValueError:
        inside_target = False
    if not inside_target:
        raise zipfile.BadZipFile(f"Attempted path traversal attack: {member.filename}")
    
    
    if not member.is_dir():
        parent_dir = os.path.dirname(target_path)
        os.makedirs(parent_dir, exist_ok=True)
        
        with zip_ref.open(member, 'r') as source, open(target_path, 'wb') as target:
            shutil.copyfileobj(source, target)
