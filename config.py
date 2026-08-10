

from Components.config import config, ConfigSubsection, ConfigText, ConfigYesNo, configfile

from . import constants


config.plugins.AzmanPanel = ConfigSubsection()



config.plugins.AzmanPanel.picon_path = ConfigText(default=constants.DEFAULT_PICON_TARGET_DIR)
config.plugins.AzmanPanel.main_menu_visible = ConfigYesNo(default=True)

def save_config():
    """Funkcja pomocnicza do zapisu konfiguracji"""
    configfile.save()
