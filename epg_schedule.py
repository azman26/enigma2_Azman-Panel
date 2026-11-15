"""EPGD publication schedule in Polish time, independent of the box timezone.

Poll the wall clock so NTP corrections, standby and DST do not shift imports.
No zoneinfo database is required on stripped-down Enigma2 images.
"""
import calendar
from datetime import datetime, timedelta, timezone
import time

HOURS = (3, 7, 11, 17, 23)
POLL_INTERVAL_MS = 60 * 1000
SCHEDULE_DESCRIPTION = "03:15, 07:15, 11:15, 17:15, 23:15 Europe/Warsaw"
FULL_SCHEDULE_DESCRIPTION = "07:15, 17:15 Europe/Warsaw"


def _dst_boundary(year, month):
    last = calendar.monthrange(year, month)[1]
    day = last - (datetime(year, month, last).weekday() + 1) % 7
    return calendar.timegm((year, month, day, 1, 0, 0))


def latest_slot(now, hours=HOURS):
    """Return the UTC timestamp of the latest completed publication buffer."""
    year = datetime.fromtimestamp(now, timezone.utc).year
    summer = _dst_boundary(year, 3) <= now < _dst_boundary(year, 10)
    local = datetime.fromtimestamp(now, timezone.utc) + timedelta(hours=2 if summer else 1)
    slots = []
    for days in (1, 0):
        date = local.date() - timedelta(days=days)
        for hour in hours:
            wall = datetime(date.year, date.month, date.day, hour, 15)
            # All slots are after the DST transition (03:00 local).
            utc = calendar.timegm(wall.timetuple()) - 3600
            if _dst_boundary(date.year, 3) <= utc < _dst_boundary(date.year, 10):
                utc -= 3600
            if utc <= now:
                slots.append(utc)
    return max(slots)


class PublicationSchedule:
    def __init__(self, clock=None, hours=HOURS):
        self.clock = clock or time.time
        self.hours = hours
        # Startup already imports once; do not repeat the preceding slot.
        self.completed = latest_slot(self.clock(), self.hours)
        self.full_refresh = False

    def due(self):
        now = self.clock()
        slot = latest_slot(now, self.hours)
        if slot <= self.completed:
            return False
        # If a full publication was missed during standby, catch up everything,
        # even when the latest publication only refreshed LG/TCL/Xiaomi.
        self.full_refresh = latest_slot(now, hours=(7, 17)) > self.completed
        # Catch up once after standby, never replay every missed publication.
        self.completed = slot
        return True
