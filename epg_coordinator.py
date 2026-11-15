"""One in-process EPG timer for all installed Azman plugins.

Each plugin ships this module so no separate dependency is required. The
runtime state belongs to Enigma2, rather than to the first plugin's package.
"""
import sys
import types

from .epg_events import import_shared_events_async
from .epg_profile import BOUQUET_PREFIX, REPORT_PREFIX, EPG_EXCLUDED_PROVIDERS
from .epg_schedule import PublicationSchedule, POLL_INTERVAL_MS

_state = sys.modules.setdefault('_azman_epg_coordinator_v1',
                               types.ModuleType('_azman_epg_coordinator_v1'))
_state.__dict__.setdefault('clients', {})
_state.__dict__.setdefault('timer', None)
_state.__dict__.setdefault('startup_pending', False)
_state.__dict__.setdefault('schedule', None)


def _log(message):
    # One log entry per client, but only one fetch/import for the receiver.
    for client in list(_state.clients.values()):
        try:
            client['logger'](message)
        except Exception:
            pass


def _tick():
    try:
        if not _state.clients:
            return
        schedule = _state.schedule
        startup = _state.startup_pending
        due = schedule.due()
        if startup or due:
            full = startup or schedule.full_refresh
            clients = list(_state.clients.values())
            _log('Shared EPG refresh: ' + ('all plugins' if full else 'FTVP LG/TCL/Xiaomi only'))
            for client in clients:
                if full and client['on_refresh'] is not None:
                    try:
                        client['on_refresh']()
                    except Exception:
                        _log('Shared EPG: mapper cache invalidation failed')
            import_shared_events_async(profiles=[c['profile'] for c in clients],
                                       full=full, logger=_log)
            _state.startup_pending = False
    except Exception as error:
        _log('Shared EPG refresh failed: %s' % type(error).__name__)
    finally:
        if _state.timer is not None:
            _state.timer.start(POLL_INTERVAL_MS, True)


def start(logger, on_refresh=None):
    """Register on GUI autostart; defer startup import to collect all clients."""
    from enigma import eTimer
    if BOUQUET_PREFIX in _state.clients:
        return
    _state.clients[BOUQUET_PREFIX] = {
        'logger': logger, 'on_refresh': on_refresh,
        'profile': (BOUQUET_PREFIX, REPORT_PREFIX, EPG_EXCLUDED_PROVIDERS),
    }
    if _state.timer is None:
        _state.schedule = PublicationSchedule(hours=(7, 17))
        _state.timer = eTimer()
        _state.timer.callback.append(_tick)
    # LG/TCL/Xiaomi extra publications are enabled only when FTVP is running.
    _state.schedule.hours = ((3, 7, 11, 17, 23)
        if 'userbouquet.azmanfreetvplayer_' in _state.clients else (7, 17))
    _state.startup_pending = True
    _state.timer.start(2000, True)
    logger('Shared EPG timer registered; full 07:15/17:15 Europe/Warsaw'
           + ('; LG/TCL/Xiaomi 03:15/11:15/23:15' if
              BOUQUET_PREFIX == 'userbouquet.azmanfreetvplayer_' else ''))


def stop():
    _state.clients.pop(BOUQUET_PREFIX, None)
    if _state.clients:
        _state.schedule.hours = ((3, 7, 11, 17, 23)
            if 'userbouquet.azmanfreetvplayer_' in _state.clients else (7, 17))
    elif _state.timer is not None:
        _state.timer.stop()
        _state.timer = None
        _state.schedule = None
        _state.startup_pending = False
