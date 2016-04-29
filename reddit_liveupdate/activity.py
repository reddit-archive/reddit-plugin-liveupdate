import collections
import datetime

from pylons import app_globals as g, tmpl_context as c
from thrift.transport.TTransport import TTransportException

from r2.lib import amqp, websockets, utils, baseplate_integration
from r2.lib.db import tdb_cassandra
from r2.models.query_cache import CachedQueryMutator

from reddit_liveupdate.models import (
    ActiveVisitorsByLiveUpdateEvent,
    LiveUpdateEvent,
    LiveUpdateActivityHistoryByEvent,
)
from reddit_liveupdate.queries import get_active_events


@baseplate_integration.with_root_span("job.liveupdate_activity")
def update_activity():
    events = {}
    event_counts = collections.Counter()

    query = (ev for ev in LiveUpdateEvent._all()
             if ev.state == "live" and not ev.banned)
    for chunk in utils.in_chunks(query, size=100):
        context_ids = {"LiveUpdateEvent_" + ev._id: ev._id for ev in chunk}

        try:
            with c.activity_service.retrying() as svc:
                infos = svc.count_activity_multi(context_ids.keys())
        except TTransportException:
            continue

        for context_id, info in infos.iteritems():
            event_id = context_ids[context_id]

            try:
                LiveUpdateActivityHistoryByEvent.record_activity(
                    event_id, info.count)
            except tdb_cassandra.TRANSIENT_EXCEPTIONS as e:
                g.log.warning("Failed to update activity history for %r: %s",
                              event_id, e)

            try:
                event = LiveUpdateEvent.update_activity(
                    event_id, info.count, info.is_fuzzed)
            except tdb_cassandra.TRANSIENT_EXCEPTIONS as e:
                g.log.warning("Failed to update event activity for %r: %s",
                              event_id, e)
            else:
                events[event_id] = event
                event_counts[event_id] = info.count

            websockets.send_broadcast(
                "/live/" + event_id,
                type="activity",
                payload={
                    "count": info.count,
                    "fuzzed": info.is_fuzzed,
                },
            )

    top_event_ids = [event_id for event_id, count in event_counts.most_common(1000)]
    top_events = [events[event_id] for event_id in top_event_ids]
    query_ttl = datetime.timedelta(days=3)
    with CachedQueryMutator() as m:
        m.replace(get_active_events(), top_events, ttl=query_ttl)

    # ensure that all the amqp messages we've put on the worker's queue are
    # sent before we allow this script to exit.
    amqp.worker.join()
