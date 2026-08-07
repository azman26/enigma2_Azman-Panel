# /usr/lib/enigma2/python/Plugins/Extensions/AzmanPanel/utils.py
# KOD Z POPRAWKĄ DLA FUNKCJI ROZPAKOWUJĄCEJ Picony

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

def log_error(exception, context_info="Unknown", **kwargs):
    # ... (ta funkcja pozostaje bez zmian) ...
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
    # <<< POCZĄTEK MODYFIKACJI - IGNOROWANIE GŁÓWNEGO FOLDERU W ZIP ---
    
    # Dzielimy ścieżkę pliku wewnątrz archiwum na części
    path_parts = member.filename.split('/')
    
    # Jeśli ścieżka ma więcej niż jedną część (tzn. jest w folderze), usuwamy pierwszą (główny folder)
    if len(path_parts) > 1:
        # Ignorujemy puste nazwy plików (mogą się zdarzyć przy folderach)
        if not path_parts[-1]:
            return
        filename = os.path.join(*path_parts[1:])
    else:
        filename = member.filename

    target_path = os.path.join(target_dir, filename)
    
    # <<< KONIEC MODYFIKACJI ---
    
    # Sprawdzenie bezpieczeństwa ścieżki z poprawną granicą katalogu.
    target_root = os.path.realpath(target_dir)
    target_real = os.path.realpath(target_path)
    try:
        inside_target = os.path.commonpath((target_root, target_real)) == target_root
    except ValueError:
        inside_target = False
    if not inside_target:
        raise zipfile.BadZipFile(f"Attempted path traversal attack: {member.filename}")
    
    # Jeśli to nie jest katalog, utwórz katalog nadrzędny i wypakuj plik
    if not member.is_dir():
        parent_dir = os.path.dirname(target_path)
        os.makedirs(parent_dir, exist_ok=True)
        with zip_ref.open(member, 'r') as source, open(target_path, 'wb') as target:
            shutil.copyfileobj(source, target)
