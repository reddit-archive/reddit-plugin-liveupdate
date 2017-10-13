"""
Real-time updates on reddit.

In addition to the standard reddit API, WebSockets play a huge role in reddit
live. Receiving push notification of changes to the thread via websockets is
much better than polling the thread repeatedly.

To connect to the websocket server, fetch
[/live/*thread*/about.json](#GET_live_{thread}_about.json) and get the
`websocket_url` field.  The websocket URL expires after a period of time; if it
does, fetch a new one from that endpoint.

Once connected to the socket, a variety of messages can come in. All messages
will be in text frames containing a JSON object with two keys: `type` and
`payload`. Live threads can send messages with many `type`s:

* `update` - a new update has been posted in the thread. the `payload` contains
  the JSON representation of the update.
* `activity` - periodic update of the viewer counts for the thread.
* `settings` - the thread's settings have changed. the `payload` is an object
  with each key being a property of the thread (as in `about.json`) and its new
  value.
* `delete` - an update has been deleted (removed from the thread).
  the `payload` is the ID of the deleted update.
* `strike` - an update has been stricken (marked incorrect and crossed out).
  the `payload` is the ID of the stricken update.
* `embeds_ready` - a previously posted update has been parsed and embedded
  media is available for it now. the `payload` contains a `liveupdate_id` and
  list of `embeds` to add to it.
* `complete` - the thread has been marked complete. no further updates will
  be sent.

See /r/live for more information.

"""
import datetime
import sys

import pytz

from pylons.i18n import N_

from r2.config.routing import not_in_sr
from r2.lib.configparse import ConfigValue
from r2.lib.js import (
    FileSource,
    LocalizedModule,
    LocaleSpecificSource,
    TemplateFileSource,
    PermissionsDataSource,
)
from r2.lib.plugin import Plugin

from reddit_liveupdate.permissions import ContributorPermissionSet


class MomentTranslations(LocaleSpecificSource):
    def get_localized_source(self, lang):
        # TODO: minify this
        source = FileSource("lib/moment-langs/%s.js" % lang)
        try:
            localized_source = source.get_source(use_built_statics=True)
        except IOError:
            print >> sys.stderr, "    WARNING: no moment.js support for %r" % lang
            return ""
        return localized_source


def Date(text):
    return datetime.datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=pytz.utc)


class LiveUpdate(Plugin):
    needs_static_build = True

    errors = {
        "LIVEUPDATE_NOT_CONTRIBUTOR":
            N_("that user is not a contributor"),
        "LIVEUPDATE_NO_INVITE_FOUND":
            N_("there is no pending invite for that thread"),
        "LIVEUPDATE_TOO_MANY_INVITES":
            N_("there are too many pending invites outstanding"),
        "LIVEUPDATE_ALREADY_CONTRIBUTOR":
            N_("that user is already a contributor"),
    }

    config = {
        ConfigValue.int: [
            "liveupdate_invite_quota",
            "liveupdate_min_score_for_discussions",
        ],

        ConfigValue.str: [
            "liveupdate_pixel_domain",
        ],

        ConfigValue.baseplate(Date): [
            "liveupdate_min_date_viewcounts",
        ],
    }

    js = {
        "liveupdate": LocalizedModule("liveupdate.js",
            "lib/page-visibility.js",
            "lib/tinycon.js",
            "lib/moment.js",
            "websocket.js",

            "liveupdate/init.js",
            "liveupdate/activity.js",
            "liveupdate/embeds.js",
            "liveupdate/event.js",
            "liveupdate/favicon.js",
            "liveupdate/listings.js",
            "liveupdate/notifications.js",
            "liveupdate/statusBar.js",
            "liveupdate/report.js",

            TemplateFileSource("liveupdate/update.html"),
            TemplateFileSource("liveupdate/separator.html"),
            TemplateFileSource("liveupdate/edit-button.html"),
            TemplateFileSource("liveupdate/reported.html"),

            PermissionsDataSource({
                "liveupdate_contributor": ContributorPermissionSet,
                "liveupdate_contributor_invite": ContributorPermissionSet,
            }),

            localized_appendices=[
                MomentTranslations(),
            ],
        ),
    }

    def add_routes(self, mc):
        mc(
            "/live",
            controller="liveupdateevents",
            action="home",
            conditions={"function": not_in_sr},
        )

        mc(
            "/live/create",
            controller="liveupdateevents",
            action="create",
            conditions={"function": not_in_sr},
        )

        mc(
            "/api/live/by_id/:names",
            action="listing",
            controller="liveupdatebyid",
        )

        mc(
            "/live/:filter",
            action="listing",
            controller="liveupdateevents",
            conditions={"function": not_in_sr},
            requirements={"filter": "open|closed|reported|active|happening_now|mine"},
        )

        mc(
            "/api/live/:action",
            controller="liveupdateevents",
            conditions={"function": not_in_sr},
            requirements={"action": "create|happening_now"},
        )

        mc("/live/:event", controller="liveupdate", action="listing",
           conditions={"function": not_in_sr}, is_embed=False)

        mc("/live/:event/embed", controller="liveupdate", action="listing",
           conditions={"function": not_in_sr}, is_embed=True)

        mc(
            "/live/:event/updates/:target",
            controller="liveupdate",
            action="focus",
            conditions={"function": not_in_sr},
        )

        mc("/live/:event/pixel",
           controller="liveupdatepixel", action="pixel",
           conditions={"function": not_in_sr})

        mc("/live/:event/:action", controller="liveupdate",
           conditions={"function": not_in_sr})

        mc("/api/live/:event/:action", controller="liveupdate",
           conditions={"function": not_in_sr})

        mc('/mediaembed/liveupdate/:event/:liveupdate/:embed_index',
           controller="liveupdateembed", action="mediaembed")

        mc('/admin/happening-now', controller='liveupdateadmin', action='happening_now')

    def load_controllers(self):
        from r2.controllers.api_docs import api_section, section_info
        api_section["live"] = "live"
        section_info["live"] = {
            "title": "live threads",
            "description": sys.modules[__name__].__doc__,
        }

        from r2.models.token import OAuth2Scope
        OAuth2Scope.scope_info["livemanage"] = {
            "id": "livemanage",
            "name": N_("Manage live threads"),
            "description":
                N_("Manage settings and contributors of live threads "
                   "I contribute to."),
        }

        from reddit_liveupdate.controllers import (
            controller_hooks,
            LiveUpdateByIDController,
            LiveUpdateController,
            LiveUpdateEventsController,
            LiveUpdatePixelController,
        )

        from r2.config.templates import api
        from reddit_liveupdate import pages
        api('liveupdateeventapp', pages.LiveUpdateEventAppJsonTemplate)
        api('liveupdatefocusapp', pages.LiveUpdateEventAppJsonTemplate)
        api('liveupdateevent', pages.LiveUpdateEventJsonTemplate)
        api('liveupdatereportedeventrow', pages.LiveUpdateEventJsonTemplate)
        api('liveupdatefeaturedevent', pages.LiveUpdateFeaturedEventJsonTemplate)
        api('liveupdate', pages.LiveUpdateJsonTemplate)
        api('liveupdatecontributortableitem',
            pages.ContributorTableItemJsonTemplate)

        controller_hooks.register_all()

        from reddit_liveupdate import scraper
        scraper.hooks.register_all()

    def declare_queues(self, queues):
        from r2.config.queues import MessageQueue
        queues.declare({
            "liveupdate_scraper_q": MessageQueue(bind_to_self=True),
        })

        queues.liveupdate_scraper_q << (
            "new_liveupdate_update",
        )

    source_root_url = "https://github.com/reddit/reddit-plugin-liveupdate/blob/master/reddit_liveupdate/"
    def get_documented_controllers(self):
        from reddit_liveupdate.controllers import (
            LiveUpdateController,
            LiveUpdateEventsController,
            LiveUpdateByIDController,
        )

        yield LiveUpdateController, "/api/live/{thread}"
        yield LiveUpdateEventsController, ""
        yield LiveUpdateByIDController, ""
