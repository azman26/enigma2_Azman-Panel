

from enigma import eTimer
from Plugins.Plugin import PluginDescriptor
from .screens import AzmanPanelMainScreen
from . import constants, utils
from .config import config
from .epg_events import import_events_async as import_epg_events_async
from .epg_coordinator import start as start_shared_epg, stop as stop_shared_epg


def main(session, **kwargs):
    session.open(AzmanPanelMainScreen)


def menu(menuid, **kwargs):
    if menuid == "mainmenu" and config.plugins.AzmanPanel.main_menu_visible.value:
        return [(constants.PLUGIN_NAME, main, "azmanpanel_mainmenu", 46)]
    return []


def _run_epg_events_import():
    import_epg_events_async(logger=lambda message: utils.log_event("EPG events: %s" % message))


def start_epg_events_timer():
    start_shared_epg(utils.log_event)


def stop_epg_events_timer():
    stop_shared_epg()


def autostart(reason, **kwargs):
    if reason == 0:
        start_epg_events_timer()
    elif reason == 1:
        stop_epg_events_timer()


def Plugins(**kwargs):
    descriptors = [
        PluginDescriptor(
            name=constants.PLUGIN_NAME,
            description="Centrum narzedzi i instalacji Azman (v%s)" % constants.PLUGIN_VERSION,
            icon="plugin.png",
            where=[PluginDescriptor.WHERE_PLUGINMENU],
            fnc=main,
        ),
        PluginDescriptor(
            name=constants.PLUGIN_NAME,
            description="Centrum narzedzi i instalacji Azman (v%s)" % constants.PLUGIN_VERSION,
            where=PluginDescriptor.WHERE_AUTOSTART,
            fnc=autostart,
        ),
    ]
    # Keep the callback registered: menu() checks the current saved setting.
    descriptors.append(PluginDescriptor(
        name=constants.PLUGIN_NAME,
        description="Centrum narzedzi i instalacji Azman",
        where=PluginDescriptor.WHERE_MENU,
        fnc=menu,
    ))
    return descriptors
