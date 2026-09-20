

from enigma import eTimer
from Plugins.Plugin import PluginDescriptor
from .screens import AzmanPanelMainScreen
from . import constants, utils
from .config import config
from .epg_events import import_events_async as import_epg_events_async


def main(session, **kwargs):
    session.open(AzmanPanelMainScreen)


def menu(menuid, **kwargs):
    if menuid == "mainmenu" and config.plugins.AzmanPanel.main_menu_visible.value:
        return [(constants.PLUGIN_NAME, main, "azmanpanel_mainmenu", 46)]
    return []


_EPG_EVENTS_TIMER = None
EPG_EVENTS_REFRESH_INTERVAL_MS = 12 * 60 * 60 * 1000


def _run_epg_events_import():
    import_epg_events_async(logger=lambda message: utils.log_event("EPG events: %s" % message))


def _on_epg_events_timer():
    _run_epg_events_import()
    if _EPG_EVENTS_TIMER is not None:
        _EPG_EVENTS_TIMER.start(EPG_EVENTS_REFRESH_INTERVAL_MS, True)


def start_epg_events_timer():
    global _EPG_EVENTS_TIMER
    if _EPG_EVENTS_TIMER is not None:
        return
    _EPG_EVENTS_TIMER = eTimer()
    _EPG_EVENTS_TIMER.callback.append(_on_epg_events_timer)
    _EPG_EVENTS_TIMER.start(EPG_EVENTS_REFRESH_INTERVAL_MS, True)
    utils.log_event("EPG events timer armed (every 12h)")


def stop_epg_events_timer():
    global _EPG_EVENTS_TIMER
    if _EPG_EVENTS_TIMER is not None:
        try:
            _EPG_EVENTS_TIMER.stop()
        except Exception:
            pass
        _EPG_EVENTS_TIMER = None


def autostart(reason, **kwargs):
    if reason == 0:
        start_epg_events_timer()
        _run_epg_events_import()
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
    if config.plugins.AzmanPanel.main_menu_visible.value:
        descriptors.append(PluginDescriptor(
            name=constants.PLUGIN_NAME,
            description="Centrum narzedzi i instalacji Azman",
            where=PluginDescriptor.WHERE_MENU,
            fnc=menu,
        ))
    return descriptors
