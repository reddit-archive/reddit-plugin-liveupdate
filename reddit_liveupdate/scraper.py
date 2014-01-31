from pylons import g

from r2.lib.hooks import HookRegistrar
from r2.lib.media import Scraper, MediaEmbed
from r2.lib.utils import UrlParser


hooks = HookRegistrar()
_EMBED_TEMPLATE = """
<!doctype html>
<html>
<head>
<style>
iframe {{
    border: 1px solid black;
}}
</style>
</head>
<body>
<iframe src="//{domain}/live/{event_id}/embed"
        width="{width}" height="{height}">
</iframe>
</body>
</html>
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
        width = 710
        height = 500

        content = _EMBED_TEMPLATE.format(
            event_id=media_object["event_id"],
            domain=g.media_domain,
            width=width,
            height=height,
        )

        return MediaEmbed(
            height=height,
            width=width,
            content=content,
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
