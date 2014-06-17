from r2.models.query_cache import CachedQueryMutator

from reddit_liveupdate import models, queries


def backfill_listings():
    queries_by_state = {
        "live": queries.get_live_events,
        "complete": queries.get_complete_events,
    }

    events = models.LiveUpdateEvent._all()

    with CachedQueryMutator() as m:
        for event in events:
            query_fn = queries_by_state[event.state]
            query = query_fn("new", "all")
            m.insert(query, [event])


backfill_listings()
