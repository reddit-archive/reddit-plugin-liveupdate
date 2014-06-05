import datetime

import pytz

from r2.lib.db.operators import desc
from r2.models.query_cache import (
    cached_query,
    CachedQueryMutator,
    filter_thing,
)

from reddit_liveupdate.models import LiveUpdateQueryCache


@cached_query(LiveUpdateQueryCache, sort=[desc("action_date")],
              filter_fn=filter_thing)
def get_reported_events():
    pass


class _LiveUpdateEventReport(object):
    def __init__(self, event):
        self.thing = event
        self.action_date = datetime.datetime.now(pytz.UTC)


def report_event(event):
    query = get_reported_events()

    with CachedQueryMutator() as m:
        m.insert(query, [_LiveUpdateEventReport(event)])


def unreport_event(event):
    query = get_reported_events()

    with CachedQueryMutator() as m:
        m.delete(query, [_LiveUpdateEventReport(event)])
