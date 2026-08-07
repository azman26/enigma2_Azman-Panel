# /usr/lib/enigma2/python/Plugins/Extensions/AzmanPanel/constants.py
# KOD Z POPRAWKI #14

# Stała wersja wydania. Format: YYYY.MM.DD-HHMM.
# Nie generować jej dynamicznie przy starcie Enigma2 — wersja ma oznaczać
# konkretne wydanie, a nie czas ostatniego uruchomienia pluginu.
PLUGIN_NAME = "Azman Panel"
PLUGIN_VERSION = "2026.08.08-0125"
PLUGIN_BUILD = "azman-panel-2026.08.08-0125"

# --- Azman OPKG Feed ---
FEED_CONF_URL = "https://raw.githubusercontent.com/azman26/azman-enigma2-repo/main/azman-feed.conf"
FEED_CONF_TARGET_PATH = "/etc/opkg/azman-feed.conf"
FEED_PACKAGES_BASE_URL = "https://azman26.github.io/azman-enigma2-repo"
# Docelowy feed prywatny dla wariantów zależnych od środowiska.
AZMAN_FEED_BASE_URL = "https://www.topolowa4.pl/azman-feed"
AZMAN_MANIFEST_URL = "https://raw.githubusercontent.com/azman26/enigma2_Azman-Panel/main/feed/manifest.json"

# --- Picons ---
PICONS_BASE_URL = "https://www.topolowa4.pl/ENIGMA2/PICONY/"
DEFAULT_PICON_TARGET_DIR = "/media/hdd/picon"
PICON_RECOMMENDED_DIRS = [
    ("/media/hdd/picon", "Dysk twardy HDD (/media/hdd/picon)"),
    ("/media/usb/picon", "Pamięć USB (/media/usb/picon)")
]

# --- EPG sources ---
SOURCES_XML_URL = "https://raw.githubusercontent.com/azman26/EPGazman/main/polandAzman.sources.xml"
SOURCES_XML_TARGET_DIR = "/etc/epgimport"
SOURCES_XML_FILENAME = "polandAzman.sources.xml"

# --- ArchivCZSK ---
ARCHIVCZSK_INSTALL_CMD = "curl -s --insecure https://raw.githubusercontent.com/archivczsk/archivczsk/main/build/archivczsk_installer.sh | sh"

# --- Bukiety IPTV PL ---
IPTV_SETTINGS_LIST_URL = "https://github.com/azman26/azmanIPTVsettings"
IPTV_SETTINGS_BASE_URL = "https://raw.githubusercontent.com/azman26/azmanIPTVsettings/main/"

# --- Bukiety FAST ---
FAST_SETTINGS_LIST_URL = "https://github.com/azman26/azmanFASTsettings"
FAST_SETTINGS_BASE_URL = "https://raw.githubusercontent.com/azman26/azmanFASTsettings/main/"

# --- Shelly Control Center ---
SHELLY_INSTALL_CMD = 'wget -q "--no-check-certificate" https://raw.githubusercontent.com/Northmount/shelly-enigma2/main/installer.sh -O - | /bin/sh'

# --- IMGW Meteo ---
IMGW_INSTALL_CMD = 'wget -q "--no-check-certificate" https://raw.githubusercontent.com/e2plugins/imgw-meteo/main/installer.sh -O - | /bin/sh'

# --- AJPanel ---
AJPANEL_INSTALL_CMD = 'wget https://raw.githubusercontent.com/AMAJamry/AJPanel/main/installer.sh -O - | /bin/sh'

# --- M3U IPTV Reader --- POPRAWIONA I OSTATECZNA KOMENDA ---
TARGET_DIR = "/usr/lib/enigma2/python/Plugins/SystemPlugins/M3UIPTV"
M3UIPTV_INSTALL_CMD = f'mkdir -p {TARGET_DIR} && wget https://github.com/DimitarCC/iptv-m3u-reader/archive/refs/heads/main.zip -O /tmp/m3uiptv.zip && unzip /tmp/m3uiptv.zip -d /tmp && cp -r /tmp/iptv-m3u-reader-main/src/* {TARGET_DIR}/ && rm -rf /tmp/m3uiptv.zip /tmp/iptv-m3u-reader-main'
