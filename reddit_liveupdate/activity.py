from pylons import g

from r2.lib import amqp, websockets, utils
from r2.lib.db import tdb_cassandra

from reddit_liveupdate.models import (
    ActiveVisitorsByLiveUpdateEvent,
    LiveUpdateEvent,
    LiveUpdateActivityHistoryByEvent,
)


ACTIVITY_FUZZING_THRESHOLD = 100


def update_activity():
    event_ids = ActiveVisitorsByLiveUpdateEvent._cf.get_range(
        column_count=1, filter_empty=False)

    for event_id, is_active in event_ids:
        count = 0

        if is_active:
            try:
                count = ActiveVisitorsByLiveUpdateEvent.get_count(event_id)
            except tdb_cassandra.TRANSIENT_EXCEPTIONS as e:
                g.log.warning("Failed to fetch activity count for %r: %s",
                              event_id, e)
                return

        try:
            LiveUpdateActivityHistoryByEvent.record_activity(event_id, count)
        except tdb_cassandra.TRANSIENT_EXCEPTIONS as e:
            g.log.warning("Failed to update activity history for %r: %s",
                          event_id, e)

        is_fuzzed = False
        if count < ACTIVITY_FUZZING_THRESHOLD:
            count = utils.fuzz_activity(count)
            is_fuzzed = True

        try:
            LiveUpdateEvent.update_activity(event_id, count, is_fuzzed)
        except tdb_cassandra.TRANSIENT_EXCEPTIONS as e:
            g.log.warning("Failed to update event activity for %r: %s",
                          event_id, e)

        websockets.send_broadcast(
            "/live/" + event_id,
            type="activity",
            payload={
                "count": count,
                "fuzzed": is_fuzzed,
            },
        )

    # ensure that all the amqp messages we've put on the worker's queue are
    # sent before we allow this script to exit.
    amqp.worker.join()
