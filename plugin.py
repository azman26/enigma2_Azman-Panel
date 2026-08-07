# /usr/lib/enigma2/python/Plugins/Extensions/AzmanPanel/plugin.py

from Plugins.Plugin import PluginDescriptor
from .screens import AzmanPanelMainScreen
from . import constants

def main(session, **kwargs):
    session.open(AzmanPanelMainScreen)

def Plugins(**kwargs):
    return [PluginDescriptor(
        name=constants.PLUGIN_NAME,
        description=f"Centrum narzędzi i instalacji Azman (v{constants.PLUGIN_VERSION})",
        icon="plugin.png",
        where=[PluginDescriptor.WHERE_PLUGINMENU], 
        fnc=main
    )]
