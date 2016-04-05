import datetime
import pytz
from mock import MagicMock

from pylons import app_globals as g

from r2.tests import RedditTestCase, MockEventQueue
from r2.lib import eventcollector
from reddit_liveupdate import events

FAKE_DATE = datetime.datetime(2005, 6, 23, 3, 14, 0, tzinfo=pytz.UTC)


class TestEventCollector(RedditTestCase):
    def setUp(self):
        self.domain_mock = self.autopatch(eventcollector, "domain")
        self.autopatch(
            g.events, "queue_production", MockEventQueue()
        )
        self.autopatch(
            g.events, "queue_test", MockEventQueue()
        )

        self.created_ts_mock = MagicMock(name="created_ts")
        self._datetime_to_millis = self.autopatch(
            events, "_datetime_to_millis",
            return_value=self.created_ts_mock)

        self.context = MagicMock(name="context")
        self.request = MagicMock(name="request")
        self.liveevent = MagicMock(name="liveevent", _date=FAKE_DATE)

    def make_payload(self, **additional):
        payload = {
            "live_thread_id": self.liveevent._id,
            "live_thread_title": self.liveevent.title,
            "live_thread_description": self.liveevent.description,
            "live_thread_created_ts": self.created_ts_mock,
            "live_thread_banned": self.liveevent.banned,
            "live_thread_banned_by": self.liveevent.banned_by,
            "live_thread_nsfw": self.liveevent.nsfw,

            'user_id': self.context.user._id,
            'user_name': self.context.user.name,

            'geoip_country': self.context.location,
            'oauth2_client_id': self.context.oauth2_client._id,
            'oauth2_client_app_type': self.context.oauth2_client.app_type,
            'oauth2_client_name': self.context.oauth2_client.name,
            'referrer_domain': self.domain_mock(),
            'referrer_url': self.request.headers.get(),
            'domain': self.request.host,
            'user_agent': self.request.user_agent,
            'user_agent_parsed': {
                'platform_version': None,
                'platform_name': None,
            },
            'obfuscated_data': {
                'client_ip': self.request.ip,
            },
        }
        payload.update(additional)
        return payload

    def test_create(self):
        g.live_config["events_collector_liveupdate_create_sample_rate"] = 1.0
        events.create_event(
            self.liveevent,
            context=self.context,
            request=self.request
        )
        g.events.queue_production.assert_event_item(
            dict(
                event_topic="live_thread_events",
                event_type="live_thread_create",
                payload=self.make_payload(),
            )
        )

    def test_update(self):
        g.live_config["events_collector_liveupdate_update_sample_rate"] = 1.0
        update = MagicMock(name="update")
        self.context.liveupdate_event = self.liveevent
        events.update_event(
            update,
            context=self.context,
            request=self.request
        )
        g.events.queue_production.assert_event_item(
            dict(
                event_topic="live_thread_events",
                event_type="live_thread_update",
                payload=self.make_payload(
                    live_thread_update_id=str(update._id),
                    live_thread_update_fullname=update._fullname,
                    live_thread_update_deleted=update.deleted,
                    live_thread_update_banned=update._spam,
                    live_thread_update_created_ts=self.created_ts_mock,
                    live_thread_update_body=update.body,
                ),
            )
        )

    def test_report(self):
        g.live_config["events_collector_liveupdate_report_sample_rate"] = 1.0
        reason = "too much orange"
        self.context.liveupdate_event = self.liveevent
        events.report_event(
            reason,
            context=self.context,
            request=self.request
        )
        g.events.queue_production.assert_event_item(
            dict(
                event_topic="live_thread_events",
                event_type="live_thread_report",
                payload=self.make_payload(process_notes=reason),
            )
        )

    def test_ban(self):
        g.live_config["events_collector_liveupdate_ban_sample_rate"] = 1.0
        self.context.liveupdate_event = self.liveevent
        events.ban_event(
            context=self.context,
            request=self.request
        )
        g.events.queue_production.assert_event_item(
            dict(
                event_topic="live_thread_events",
                event_type="live_thread_ban",
                payload=self.make_payload(),
            )
        )

    def test_close_event(self):
        g.live_config["events_collector_liveupdate_close_sample_rate"] = 1.0
        self.context.liveupdate_event = self.liveevent
        events.close_event(
            context=self.context,
            request=self.request
        )
        g.events.queue_production.assert_event_item(
            dict(
                event_topic="live_thread_events",
                event_type="live_thread_close",
                payload=self.make_payload(),
            )
        )
