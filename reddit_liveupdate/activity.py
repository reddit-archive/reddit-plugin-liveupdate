from r2.lib import amqp, websockets, utils

from reddit_liveupdate.models import (
    ActiveVisitorsByLiveUpdateEvent,
    LiveUpdateEvent,
)


ACTIVITY_FUZZING_THRESHOLD = 100


def update_activity():
    event_ids = ActiveVisitorsByLiveUpdateEvent._cf.get_range(
        column_count=1, filter_empty=False)

    for event_id, is_active in event_ids:
        count = 0
        if is_active:
            count = ActiveVisitorsByLiveUpdateEvent.get_count(event_id)

        LiveUpdateEvent.update_activity(event_id, count)

        is_fuzzed = False
        if count < ACTIVITY_FUZZING_THRESHOLD:
            count = utils.fuzz_activity(count)
            is_fuzzed = True

        payload = {
            "count": count,
            "fuzzed": is_fuzzed,
        }

        websockets.send_broadcast(
            "/live/" + event_id, type="activity", payload=payload)

    # ensure that all the amqp messages we've put on the worker's queue are
    # sent before we allow this script to exit.
    amqp.worker.join()
