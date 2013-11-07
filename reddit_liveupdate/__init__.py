from pylons.i18n import N_

from r2.config.routing import not_in_sr
from r2.lib.configparse import ConfigValue
from r2.lib.js import Module, LocalizedModule, TemplateFileSource
from r2.lib.plugin import Plugin


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
            "timetext.js",
            "liveupdate.js",
        ),
        "liveupdate-editor": Module("liveupdate-editor.js",
            "liveupdate-editor.js",
            TemplateFileSource("liveupdate/edit-buttons.html"),
        ),
    }

    errors = {
        "INVALID_TIMEZONE": N_("that is not a valid timezone"),
    }

    def add_routes(self, mc):
        mc("/live/:event", controller="liveupdate", action="listing",
           conditions={"function": not_in_sr})

        mc("/live/:event/pixel",
           controller="liveupdatepixel", action="pixel",
           conditions={"function": not_in_sr})

        mc("/live/:event/:action", controller="liveupdate",
           conditions={"function": not_in_sr})

        mc("/api/live/:event/:action", controller="liveupdate",
           conditions={"function": not_in_sr})

    def load_controllers(self):
        from reddit_liveupdate.controllers import (
            LiveUpdateController,
            LiveUpdatePixelController,
        )

        from r2.config.templates import api
        from reddit_liveupdate import pages
        api('liveupdateevent', pages.LiveUpdateEventJsonTemplate)
        api('liveupdate', pages.LiveUpdateJsonTemplate)
