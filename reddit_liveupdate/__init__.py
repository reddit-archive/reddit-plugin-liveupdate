import sys

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
        if not source.path:
            print >> sys.stderr, "    WARNING: no moment.js support for %r" % lang
            return ""
        return source.get_source()


class LiveUpdate(Plugin):
    needs_static_build = True

    errors = {
        "LIVEUPDATE_NO_INVITE_FOUND":
            N_("there is no pending invite for that stream"),
        "LIVEUPDATE_TOO_MANY_INVITES":
            N_("there are too many pending invites outstanding"),
        "LIVEUPDATE_ALREADY_CONTRIBUTOR":
            N_("that user is already a contributor"),
    }

    config = {
        ConfigValue.int: [
            "liveupdate_invite_quota",
        ],

        ConfigValue.str: [
            "liveupdate_pixel_domain",
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
            "/live/:action",
            controller="liveupdateevents",
            conditions={"function": not_in_sr},
            requirements={"action": "create|reports"},
        )

        mc(
            "/api/live/:action",
            controller="liveupdateevents",
            conditions={"function": not_in_sr},
            requirements={"action": "create"},
        )

        mc("/live/:event", controller="liveupdate", action="listing",
           conditions={"function": not_in_sr}, is_embed=False)

        mc("/live/:event/embed", controller="liveupdate", action="listing",
           conditions={"function": not_in_sr}, is_embed=True)

        mc("/live/:event/pixel",
           controller="liveupdatepixel", action="pixel",
           conditions={"function": not_in_sr})

        mc("/live/:event/:action", controller="liveupdate",
           conditions={"function": not_in_sr})

        mc("/api/live/:event/:action", controller="liveupdate",
           conditions={"function": not_in_sr})

        mc('/mediaembed/liveupdate/:event/:liveupdate/:embed_index',
           controller="liveupdateembed", action="mediaembed")

    def load_controllers(self):
        from reddit_liveupdate.controllers import (
            LiveUpdateController,
            LiveUpdateEventsController,
            LiveUpdatePixelController,
        )

        from r2.config.templates import api
        from reddit_liveupdate import pages
        api('liveupdateeventapp', pages.LiveUpdateEventAppJsonTemplate)
        api('liveupdateevent', pages.LiveUpdateEventJsonTemplate)
        api('liveupdatereportedeventrow', pages.LiveUpdateEventJsonTemplate)
        api('liveupdate', pages.LiveUpdateJsonTemplate)

        from reddit_liveupdate import scraper
        scraper.hooks.register_all()

    def declare_queues(self, queues):
        from r2.config.queues import MessageQueue
        queues.declare({
            "liveupdate_scraper_q": MessageQueue(bind_to_self=True),
        })
