


import os
import zipfile
import traceback
import datetime
import shutil
import re
import tempfile

LOG_FILE = "/tmp/Azman_Panel.log"
MAX_LOG_SIZE = 512 * 1024
LOG_TAIL_SIZE = 384 * 1024
BOUQUET_FILENAME_RE = re.compile(r"^userbouquet\.[A-Za-z0-9._-]+\.tv$")

def _sanitize_log_value(key, value):
    if str(key).lower() in ("token", "authorization", "password", "secret", "url", "source", "source_url"):
        return "[ukryto]"
    text = str(value)
    text = re.sub(r"([?&](?:token|key|auth|authorization)=)[^&\s]+", r"\1***", text, flags=re.IGNORECASE)
    return re.sub(r"https?://[^\s'\"]+", "[adres ukryty]", text, flags=re.IGNORECASE)

def _rotate_log():
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_SIZE:
            with open(LOG_FILE, "rb") as handle:
                handle.seek(-LOG_TAIL_SIZE, os.SEEK_END)
                data = handle.read()
            with open(LOG_FILE, "wb") as handle:
                handle.write(b"--- Azman Panel log: zachowano ostatnie wpisy ---\n")
                handle.write(data)
    except OSError:
        pass

def _write_log(level, message, **kwargs):
    try:
        _rotate_log()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        details = " ".join("%s=%s" % (key, _sanitize_log_value(key, value)) for key, value in sorted(kwargs.items()))
        line = "[%s] [%s] %s" % (timestamp, level, _sanitize_log_value("message", message))
        if details:
            line += " | " + details
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception as error:
        print("[AzmanPanel] CRITICAL LOGGING ERROR: %s" % error)

def log_event(message, **kwargs):
    _write_log("INFO", message, **kwargs)

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
        _write_log("ERROR", "%s: %s: %s" % (context_info, type(exception).__name__, exception), **kwargs)
        trace = traceback.format_exc()
        if trace and trace.strip() != "NoneType: None":
            with open(LOG_FILE, "a", encoding="utf-8") as handle:
                handle.write(trace + "\n")
        print("[AzmanPanel] Error details have been written to: %s" % LOG_FILE)
    except Exception as log_error:
        print("[AzmanPanel] CRITICAL LOGGING ERROR: %s" % log_error)


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
