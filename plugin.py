# /usr/lib/enigma2/python/Plugins/Extensions/AzmanPanel/plugin.py

from Plugins.Plugin import PluginDescriptor
from .screens import AzmanPanelMainScreen
from . import constants
from .config import config


def main(session, **kwargs):
    session.open(AzmanPanelMainScreen)


def menu(menuid, **kwargs):
    if menuid == "mainmenu" and config.plugins.AzmanPanel.main_menu_visible.value:
        return [(constants.PLUGIN_NAME, main, "azmanpanel_mainmenu", 46)]
    return []


def Plugins(**kwargs):
    descriptors = [PluginDescriptor(
        name=constants.PLUGIN_NAME,
        description="Centrum narzedzi i instalacji Azman (v%s)" % constants.PLUGIN_VERSION,
        icon="plugin.png",
        where=[PluginDescriptor.WHERE_PLUGINMENU],
        fnc=main,
    )]
    if config.plugins.AzmanPanel.main_menu_visible.value:
        descriptors.append(PluginDescriptor(
            name=constants.PLUGIN_NAME,
            description="Centrum narzedzi i instalacji Azman",
            where=PluginDescriptor.WHERE_MENU,
            fnc=menu,
        ))
    return descriptors
