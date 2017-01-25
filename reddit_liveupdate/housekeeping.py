import datetime

import pytz

from pylons import app_globals as g
from pycassa.cassandra.ttypes import NotFoundException

from reddit_liveupdate.controllers import close_event
from reddit_liveupdate.models import LiveUpdateEvent, LiveUpdateStream


# how long a live thread must go without being updated before we consider it
# abandoned and eligible to be automatically closed.
DERELICTION_THRESHOLD = datetime.timedelta(days=7)


def close_abandoned_threads():
    """Find live threads that are abandoned and close them.

    Jobs like the activity tracker iterate through all open live threads, so
    closing abandoned threads removes some effort from them and is generally
    good for cleanliness.

    """
    now = datetime.datetime.now(pytz.UTC)
    horizon = now - DERELICTION_THRESHOLD

    for event in LiveUpdateEvent._all():
        if event.state != "live" or event.banned:
            continue

        try:
            columns = LiveUpdateStream._cf.get(
                event._id, column_reversed=True, column_count=1)
        except NotFoundException:
            event_last_modified = event._date
        else:
            updates = LiveUpdateStream._column_to_obj([columns])
            most_recent_update = updates.pop()
            event_last_modified = most_recent_update._date

        if event_last_modified < horizon:
            g.log.warning("Closing %s for inactivity.", event._id)
            close_event(event)
