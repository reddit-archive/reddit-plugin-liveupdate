import itertools

import pytz

from babel.dates import format_time
from pylons import c


def pairwise(iterable):
    a, b = itertools.tee(iterable)
    next(b, None)
    return itertools.izip(a, b)


def pretty_time(dt):
    display_tz = pytz.timezone(c.liveupdate_event.timezone)

    return format_time(
        time=dt,
        tzinfo=display_tz,
        format="HH:mm z",
        locale=c.locale,
    )
