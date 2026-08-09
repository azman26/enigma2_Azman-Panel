# /usr/lib/enigma2/python/Plugins/Extensions/AzmanPanel/config.py

from Components.config import config, ConfigSubsection, ConfigText, ConfigYesNo, configfile
# Importujemy stałe z naszego nowego, czystego pliku
from . import constants

# Inicjalizacja sekcji konfiguracyjnej dla pluginu
config.plugins.AzmanPanel = ConfigSubsection()

# Definicja opcji - przechowuje ostatnio wybraną ścieżkę do picon
# Ta linia teraz zadziała poprawnie, bo importuje wartość z w pełni załadowanego modułu constants
config.plugins.AzmanPanel.picon_path = ConfigText(default=constants.DEFAULT_PICON_TARGET_DIR)
config.plugins.AzmanPanel.main_menu_visible = ConfigYesNo(default=True)

def save_config():
    """Funkcja pomocnicza do zapisu konfiguracji"""
    configfile.save()
