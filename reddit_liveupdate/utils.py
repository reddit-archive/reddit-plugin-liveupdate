import datetime
import itertools

import pytz

from babel.dates import format_time, format_datetime
from pylons import c


def pairwise(iterable):
    a, b = itertools.tee(iterable)
    next(b, None)
    return itertools.izip(a, b)


def pretty_time(dt):
    display_tz = pytz.timezone(c.liveupdate_event.timezone)
    today = datetime.datetime.now(display_tz).date()
    date = dt.astimezone(display_tz).date()

    if date == today:
        return format_time(
            time=dt,
            tzinfo=display_tz,
            format="HH:mm z",
            locale=c.locale,
        )
    elif today - date < datetime.timedelta(days=365):
        return format_datetime(
            datetime=dt,
            tzinfo=display_tz,
            format="dd MMM HH:mm z",
            locale=c.locale,
        )
    else:
        return format_datetime(
            datetime=dt,
            tzinfo=display_tz,
            format="dd MMM YYYY HH:mm z",
            locale=c.locale,
        )
