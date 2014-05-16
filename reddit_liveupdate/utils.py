import datetime
import itertools

import pytz

from babel.dates import format_datetime
from pylons import c

from r2.lib import websockets, template_helpers


def pairwise(iterable):
    a, b = itertools.tee(iterable)
    next(b, None)
    return itertools.izip(a, b)


def pretty_time(dt, allow_relative=True):
    display_tz = pytz.timezone(c.liveupdate_event.timezone)
    ago = datetime.datetime.now(pytz.UTC) - dt

    if allow_relative and ago < datetime.timedelta(hours=24):
        return template_helpers.simplified_timesince(dt)
    elif dt.date() == datetime.datetime.now(display_tz).date():
        return format_datetime(
            datetime=dt,
            tzinfo=display_tz,
            format="HH:mm",
            locale=c.locale,
        )
    elif ago < datetime.timedelta(days=365):
        return format_datetime(
            datetime=dt,
            tzinfo=display_tz,
            format="dd MMM HH:mm",
            locale=c.locale,
        )
    else:
        return format_datetime(
            datetime=dt,
            tzinfo=display_tz,
            format="dd MMM YYYY HH:mm",
            locale=c.locale,
        )


def send_event_broadcast(event_id, type, payload):
    """ Send a liveupdate broadcast for a specific event. """
    websockets.send_broadcast(namespace="/live/" + event_id,
                              type=type,
                              payload=payload)
