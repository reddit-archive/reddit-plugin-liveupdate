import datetime
import itertools

import pytz

from babel.dates import format_time, format_datetime
from pylons import c
from r2.lib import websockets


def pairwise(iterable):
    a, b = itertools.tee(iterable)
    next(b, None)
    return itertools.izip(a, b)


def pretty_time(dt, include_timezone=True):
    display_tz = pytz.timezone(c.liveupdate_event.timezone)
    today = datetime.datetime.now(display_tz).date()
    date = dt.astimezone(display_tz).date()

    if include_timezone:
        format_suffix = " z"
    else:
        format_suffix = ""

    if date == today:
        return format_time(
            time=dt,
            tzinfo=display_tz,
            format="HH:mm" + format_suffix,
            locale=c.locale,
        )
    elif today - date < datetime.timedelta(days=365):
        return format_datetime(
            datetime=dt,
            tzinfo=display_tz,
            format="dd MMM HH:mm" + format_suffix,
            locale=c.locale,
        )
    else:
        return format_datetime(
            datetime=dt,
            tzinfo=display_tz,
            format="dd MMM YYYY HH:mm" + format_suffix,
            locale=c.locale,
        )


def send_event_broadcast(event_id, type, payload):
    """ Send a liveupdate broadcast for a specific event. """
    websockets.send_broadcast(namespace="/live/" + event_id,
                              type=type,
                              payload=payload)
