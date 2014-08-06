import urllib
import urlparse

from pylons import g, c

from r2.lib.hooks import HookRegistrar
from r2.lib.media import Scraper, MediaEmbed
from r2.lib.utils import UrlParser


hooks = HookRegistrar()
_EMBED_TEMPLATE = """
<div class="psuedo-selftext">
  <iframe src="{url}" height="{height}"></iframe>
</div>
"""


class _LiveUpdateScraper(Scraper):
    def __init__(self, event_id):
        self.event_id = event_id

    def _make_media_object(self):
        return {
            "type": "liveupdate",
            "event_id": self.event_id,
        }

    def scrape(self):
        return (
            None,
            self._make_media_object(),
            self._make_media_object(),
        )

    @classmethod
    def media_embed(cls, media_object):
        height = 500

        params = {}
        if c.user.pref_show_stylesheets:
            params["stylesr"] = c.site.name

        url = urlparse.urlunparse((
            None,
            g.domain,
            "/live/%s/embed" % media_object["event_id"],
            None,
            urllib.urlencode(params),
            None,
        ))

        content = _EMBED_TEMPLATE.format(
            url=url,
            height=height,
        )

        return MediaEmbed(
            height=height,
            width=710,
            content=content,
            sandbox=False,
        )


@hooks.on("scraper.factory")
def make_scraper(url):
    parsed = UrlParser(url)

    if parsed.is_reddit_url():
        if parsed.path.startswith("/live/"):
            try:
                event_id = parsed.path.split("/")[2]
            except IndexError:
                return
            else:
                return _LiveUpdateScraper(event_id)


@hooks.on("scraper.media_embed")
def make_media_embed(media_object):
    if media_object.get("type") == "liveupdate":
        return _LiveUpdateScraper.media_embed(media_object)
