from pylons.i18n import N_

from r2.config.routing import not_in_sr
from r2.lib.configparse import ConfigValue
from r2.lib.js import (
    LocalizedModule,
    TemplateFileSource,
    PermissionsDataSource,
)
from r2.lib.plugin import Plugin

from reddit_liveupdate.permissions import ReporterPermissionSet


class LiveUpdate(Plugin):
    needs_static_build = True

    config = {
        ConfigValue.str: [
            "liveupdate_pixel_domain",
        ],
    }

    js = {
        "liveupdate": LocalizedModule("liveupdate.js",
            "lib/iso8601.js",
            "lib/visibility.js",
            "lib/tinycon.js",
            "websocket.js",
            "liveupdate.js",
        ),
        "liveupdate-reporter": LocalizedModule("liveupdate-reporter.js",
            "liveupdate-reporter.js",
            TemplateFileSource("liveupdate/edit-buttons.html"),
            PermissionsDataSource({
                "liveupdate_reporter": ReporterPermissionSet,
            }),
        ),
    }

    errors = {
        "INVALID_TIMEZONE": N_("that is not a valid timezone"),
    }

    def add_routes(self, mc):
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
            LiveUpdatePixelController,
        )

        from r2.config.templates import api
        from reddit_liveupdate import pages
        api('liveupdateevent', pages.LiveUpdateEventJsonTemplate)
        api('liveupdate', pages.LiveUpdateJsonTemplate)

        from reddit_liveupdate import scraper
        scraper.hooks.register_all()

    def declare_queues(self, queues):
        from r2.config.queues import MessageQueue
        queues.declare({
            "liveupdate_scraper_q": MessageQueue(bind_to_self=True),
        })
