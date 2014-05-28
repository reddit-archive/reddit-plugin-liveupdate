import datetime

import pytz

from babel.dates import format_datetime
from pylons import c

from r2.lib import websockets, template_helpers


def pretty_time(dt, allow_relative=True):
    ago = datetime.datetime.now(pytz.UTC) - dt

    if allow_relative and ago < datetime.timedelta(hours=24):
        return template_helpers.simplified_timesince(dt)
    elif dt.date() == datetime.datetime.now(pytz.UTC).date():
        return format_datetime(
            datetime=dt,
            tzinfo=pytz.UTC,
            format="HH:mm",
            locale=c.locale,
        )
    elif ago < datetime.timedelta(days=365):
        return format_datetime(
            datetime=dt,
            tzinfo=pytz.UTC,
            format="dd MMM HH:mm",
            locale=c.locale,
        )
    else:
        return format_datetime(
            datetime=dt,
            tzinfo=pytz.UTC,
            format="dd MMM YYYY HH:mm",
            locale=c.locale,
        )


def send_event_broadcast(event_id, type, payload):
    """ Send a liveupdate broadcast for a specific event. """
    websockets.send_broadcast(namespace="/live/" + event_id,
                              type=type,
                              payload=payload)
