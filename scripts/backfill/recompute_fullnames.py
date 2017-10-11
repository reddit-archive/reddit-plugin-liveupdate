import collections

from pycassa.columnfamily import gm_timestamp

from r2.models.query_cache import CachedQueryMutator, MAX_CACHED_ITEMS

from reddit_liveupdate import models, queries


def recompute_listings():
    # when removing the _fullname override from LiveUpdateEvent, the format of
    # event fullnames changed. this recomputes the static listings so that they
    # contain appropriate data going forward.
    #
    # this does not do anything to the active or reported listings. in the
    # prior case, we assume it will be regenerated properly one minute from
    # now. in the latter case, humans should ensure that the listing is empty
    # of reports before running this job.

    items_by_state = collections.defaultdict(list)
    queries_by_state = {
        "live": queries.get_live_events,
        "complete": queries.get_complete_events,
    }

    for event in models.LiveUpdateEvent._all():
        items_by_state[event.state].append(event)

    timestamp = gm_timestamp()
    with CachedQueryMutator() as m:
        for state, query_fn in queries_by_state.iteritems():
            query = query_fn("new", "all")

            items = items_by_state[state]
            sorted_items = sorted(items, key=lambda ev: ev._date, reverse=True)
            listing = [item for item in sorted_items][:MAX_CACHED_ITEMS]
            cols = query._cols_from_things(listing)

            query._raw_replace(
                mutator=m,
                cols=cols,
                ttl=None,
                job_timestamp=timestamp,
                clobber=True,
            )


recompute_listings()
