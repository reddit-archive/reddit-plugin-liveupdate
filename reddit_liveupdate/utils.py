import datetime

import pytz

from babel.dates import format_datetime
from pylons import tmpl_context as c

from r2.lib import websockets, template_helpers


def pretty_time(dt, allow_relative=True):
    ago = datetime.datetime.now(pytz.UTC) - dt

    if allow_relative and ago < datetime.timedelta(hours=24):
        return template_helpers.simplified_timesince(dt)
    elif dt.date() == datetime.datetime.now(pytz.UTC).date():
        date_format="HH:mm"
    elif ago < datetime.timedelta(days=365):
        date_format="dd MMM HH:mm"
    else:
        date_format="dd MMM YYYY HH:mm"

    return format_datetime(
        datetime=dt,
        tzinfo=pytz.UTC,
        format=date_format,
        locale=c.locale,
    )


def send_event_broadcast(event_id, type, payload):
    """ Send a liveupdate broadcast for a specific event. """
    websockets.send_broadcast(namespace="/live/" + event_id,
                              type=type,
                              payload=payload)
