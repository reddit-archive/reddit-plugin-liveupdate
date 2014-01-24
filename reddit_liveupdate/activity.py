from r2.lib import amqp, websockets

from reddit_liveupdate.models import ActiveVisitorsByLiveUpdateEvent


def broadcast_update():
    event_ids = ActiveVisitorsByLiveUpdateEvent._cf.get_range(
        column_count=1, filter_empty=False)

    for event_id, is_active in event_ids:
        if is_active:
            count, is_fuzzed = ActiveVisitorsByLiveUpdateEvent.get_count(
                event_id, cached=False)
        else:
            count, is_fuzzed = 0, False

        payload = {
            "count": count,
            "fuzzed": is_fuzzed,
        }

        websockets.send_broadcast(
            "/live/" + event_id, type="activity", payload=payload)

    amqp.worker.join()
