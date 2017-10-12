import datetime

import pytz

from r2.lib.db.operators import desc
from r2.models.query_cache import (
    cached_query,
    CachedQueryMutator,
    filter_thing,
    FakeQuery,
)

from reddit_liveupdate.models import LiveUpdateQueryCache


@cached_query(LiveUpdateQueryCache)
def get_active_events():
    return FakeQuery(sort=[desc("active_visitors")], precomputed=True)


@cached_query(LiveUpdateQueryCache)
def get_live_events(sort, time):
    assert sort == "new" and time == "all"
    return FakeQuery(sort=[desc("date")])


@cached_query(LiveUpdateQueryCache)
def get_complete_events(sort, time):
    assert sort == "new" and time == "all"
    return FakeQuery(sort=[desc("date")])


def create_event(event):
    with CachedQueryMutator() as m:
        m.insert(get_live_events("new", "all"), [event])


def complete_event(event):
    with CachedQueryMutator() as m:
        m.delete(get_live_events("new", "all"), [event])
        m.insert(get_complete_events("new", "all"), [event])


@cached_query(LiveUpdateQueryCache, filter_fn=filter_thing)
def get_reported_events():
    return FakeQuery(sort=[desc("action_date")])


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


@cached_query(LiveUpdateQueryCache)
def get_contributor_events(user):
    return FakeQuery(sort=[desc("date")])


def add_contributor(event, user):
    with CachedQueryMutator() as m:
        m.insert(get_contributor_events(user), [event])


def remove_contributor(event, user):
    with CachedQueryMutator() as m:
        m.delete(get_contributor_events(user), [event])
