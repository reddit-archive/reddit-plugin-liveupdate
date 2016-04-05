from pylons import app_globals as g

from r2.lib.eventcollector import Event, _datetime_to_millis
from r2.lib.utils import sampled


class LiveUpdateEvent(Event):
    def __init__(self, lu_event, **kw):
        kw.setdefault("topic", "live_thread_events")
        super(LiveUpdateEvent, self).__init__(**kw)

        self.add("live_thread_id", lu_event._id)
        self.add_text("live_thread_title", lu_event.title)
        self.add_text("live_thread_description", lu_event.description)
        self.add(
            "live_thread_created_ts",
            _datetime_to_millis(lu_event._date)
        )
        if lu_event.banned:
            self.add_text("live_thread_banned_by", lu_event.banned_by)

        self.add_if_true("live_thread_banned", lu_event.banned)
        self.add_if_true("live_thread_nsfw", lu_event.nsfw)

    def add_if_true(self, key, value):
        if value:
            self.add(key, value)


@sampled("events_collector_liveupdate_create_sample_rate")
def create_event(lu_event, request=None, context=None):
    event = LiveUpdateEvent(
        lu_event,
        event_type="live_thread_create",
        time=lu_event._date,
        request=request,
        context=context,
    )
    g.events.save_event(event)


@sampled("events_collector_liveupdate_report_sample_rate")
def report_event(reason, context, request=None):
    event = LiveUpdateEvent(
        context.liveupdate_event,
        event_type="live_thread_report",
        request=request,
        context=context,
    )

    event.add("process_notes", reason)
    g.events.save_event(event)


@sampled("events_collector_liveupdate_ban_sample_rate")
def ban_event(context, request=None):
    event = LiveUpdateEvent(
        context.liveupdate_event,
        event_type="live_thread_ban",
        request=request,
        context=context,
    )
    g.events.save_event(event)


@sampled("events_collector_liveupdate_update_sample_rate")
def update_event(update, context, stricken=False, request=None):
    event = LiveUpdateEvent(
        context.liveupdate_event,
        event_type="live_thread_update",
        request=request,
        context=context,
    )
    event.add_if_true("live_thread_update_stricken", stricken)
    event.add("live_thread_update_id", str(update._id))
    event.add("live_thread_update_fullname", update._fullname)
    event.add_if_true("live_thread_update_deleted", update.deleted)
    event.add_if_true("live_thread_update_banned", update._spam)
    event.add(
        "live_thread_update_created_ts", _datetime_to_millis(update._date))
    if hasattr(update, "body"):
        event.add_text("live_thread_update_body", update.body)

    g.events.save_event(event)


@sampled("events_collector_liveupdate_close_sample_rate")
def close_event(context, request=None):
    event = LiveUpdateEvent(
        context.liveupdate_event,
        event_type="live_thread_close",
        request=request,
        context=context,
    )
    g.events.save_event(event)
