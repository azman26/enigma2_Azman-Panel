





PLUGIN_NAME = "Azman Panel"
PLUGIN_VERSION = "2026.08.17-1507"
PLUGIN_BUILD = "azman-panel-2026.08.17-1507"


FEED_CONF_URL = "https://raw.githubusercontent.com/azman26/azman-enigma2-repo/main/azman-feed.conf"
FEED_CONF_TARGET_PATH = "/etc/opkg/azman-feed.conf"
FEED_PACKAGES_BASE_URL = "https://azman26.github.io/azman-enigma2-repo"

AZMAN_FEED_BASE_URL = "https://www.topolowa4.pl/azman-feed"
AZMAN_MANIFEST_URL = "https://raw.githubusercontent.com/azman26/enigma2_Azman-Panel/main/feed/manifest.json"
AZMAN_PACKAGE_URL_API = "https://www.topolowa4.pl/api/package-url.php"


PICONS_BASE_URL = "https://www.topolowa4.pl/api/picons-list.php"
PICON_URL_API = "https://www.topolowa4.pl/api/picon-url.php"
DEFAULT_PICON_TARGET_DIR = "/media/hdd/picon"
MYRADIOONLINE_API_URL = (
    "https://myradioonline.pl/radio-api/get-radios-v2/app-auth/andr1439/"
    "9dcc7a63f7426ed590982a7ddfa5b56ad820818df50550428bdfa4db3fbbe498299231aedde1577c3ef6b43b7a66243eb5df62864e439e329a0dc2d712e43d29"
)
MYRADIOONLINE_BOUQUET_FILENAME = "userbouquet.azmanpanel_myradioonline.tv"
POLSKIE_RADIO_BOUQUET_FILENAME = "userbouquet.azmanpanel_polskieradio.tv"
RMFON_BOUQUET_FILENAME = "userbouquet.azmanpanel_rmfon.tv"
EUROZET_BOUQUET_FILENAME = "userbouquet.azmanpanel_eurozet.tv"
IPTVORG_BOUQUET_FILENAME = "userbouquet.azmanpanel_iptvorg_pl.tv"
LGCHANNELSPL_BOUQUET_FILENAME = "userbouquet.azmanpanel_lgchannelspl.tv"
LGCHANNELSPL_PLAYLIST_URL = "https://www.apsattv.com/pllg.m3u"
SATELLITES_XML_SOURCES = (
    ("oe_alliance", "OE-Alliance", "https://raw.githubusercontent.com/oe-alliance/oe-alliance-tuxbox-common/refs/heads/master/src/satellites.xml"),
    ("openpli", "OpenPLi", "https://raw.githubusercontent.com/OpenPLi/tuxbox-xml/master/xml/satellites.xml"),
)
RMFON_API_URL = "https://api.rmfon.pl/"
EUROZET_API_URL = "https://player.chillizet.pl/api/"
EUROZET_STATIONS = (("radiozet", "Radio ZET"), ("antyradio", "ANTYRADIO"), ("meloradio", "Meloradio"), ("chillizet", "Chillizet"))
POLSKIE_RADIO_STREAMS = (
    ("Jedynka", "https://stream11.polskieradio.pl/pr1/pr1.sdp/playlist.m3u8"),
    ("Dwójka", "https://stream12.polskieradio.pl/pr2/pr2.sdp/playlist.m3u8"),
    ("Trójka", "https://stream13.polskieradio.pl/pr3/pr3.sdp/playlist.m3u8"),
    ("Czwórka", "https://stream14.polskieradio.pl/pr4/pr4.sdp/playlist.m3u8"),
    ("Polskie Radio 24", "https://stream15.polskieradio.pl/pr24/pr24.sdp/playlist.m3u8"),
    ("Polskie Radio Chopin", "https://stream85.polskieradio.pl/live/rytm.sdp/playlist.m3u8"),
    ("Polskie Radio Dzieciom", "https://stream85.polskieradio.pl/live/radio_dzieciom.sdp/playlist.m3u8"),
    ("Polskie Radio Kierowców", "https://stream10.polskieradio.pl/prk/rdk.sdp/playlist.m3u"),
    ("Polskie Radio dla Zagranicy DAB+", "https://stream85.polskieradio.pl/pr5/pr5_dab.sdp/playlist.m3u8"),
    ("Polskie Radio dla Zagranicy Wschód", "https://stream85.polskieradio.pl/pr5/pr5_wsch.sdp/playlist.m3u8"),
    ("Polskie Radio dla Zagranicy Polska", "https://stream85.polskieradio.pl/pr5/pr5.sdp/playlist.m3u8"),
    ("Polskie Radio dla Ukrainy", "https://stream85.polskieradio.pl/radio_ukraina/ukraina.stream/playlist.m3u8"),
)
PICON_RECOMMENDED_DIRS = [
    ("/media/hdd/picon", "Dysk twardy HDD (/media/hdd/picon)"),
    ("/media/usb/picon", "Pamięć USB (/media/usb/picon)")
]


ARCHIVCZSK_INSTALL_CMD = "curl -s --insecure https://raw.githubusercontent.com/archivczsk/archivczsk/main/build/archivczsk_installer.sh | sh"


BOUQUETS_LIST_API = "https://www.topolowa4.pl/api/bouquets-list.php"
BOUQUET_URL_API = "https://www.topolowa4.pl/api/bouquet-url.php"


SHELLY_INSTALL_CMD = 'wget -q "--no-check-certificate" https://raw.githubusercontent.com/Northmount/shelly-enigma2/main/installer.sh -O - | /bin/sh'


IMGW_INSTALL_CMD = 'wget -q "--no-check-certificate" https://raw.githubusercontent.com/e2plugins/imgw-meteo/main/installer.sh -O - | /bin/sh'


AJPANEL_INSTALL_CMD = 'wget https://raw.githubusercontent.com/AMAJamry/AJPanel/main/installer.sh -O - | /bin/sh'


TARGET_DIR = "/usr/lib/enigma2/python/Plugins/SystemPlugins/M3UIPTV"
M3UIPTV_INSTALL_CMD = f'mkdir -p {TARGET_DIR} && wget https://github.com/DimitarCC/iptv-m3u-reader/archive/refs/heads/main.zip -O /tmp/m3uiptv.zip && unzip /tmp/m3uiptv.zip -d /tmp && cp -r /tmp/iptv-m3u-reader-main/src/* {TARGET_DIR}/ && rm -rf /tmp/m3uiptv.zip /tmp/iptv-m3u-reader-main'
