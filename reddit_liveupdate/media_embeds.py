import json
import re
import uuid

from urllib2 import (
    HTTPError,
    URLError,
)

import requests

from pylons import g

from r2.lib import amqp
from r2.lib.db import tdb_cassandra
from r2.lib.media import MediaEmbed, Scraper, get_media_embed
from r2.lib.utils import sanitize_url

from reddit_liveupdate import pages
from reddit_liveupdate.models import LiveUpdateStream, LiveUpdateEvent
from reddit_liveupdate.utils import send_event_broadcast


_EMBED_WIDTH = 485


def get_live_media_embed(media_object):
    if media_object['type'] == "twitter.com":
        return _TwitterScraper.media_embed(media_object)
    if media_object["type"] == "embedly-card":
        return _EmbedlyCardFallbackScraper.media_embed(media_object)
    return get_media_embed(media_object)


def queue_parse_embeds(event, liveupdate):
    msg = json.dumps({
        'liveupdate_id': unicode(liveupdate._id),  # serializing UUID
        'event_id': event._id,  # Already a string
    })
    amqp.add_item('liveupdate_scraper_q', msg)


def parse_embeds(event_id, liveupdate_id, maxwidth=_EMBED_WIDTH):
    """Find, scrape, and store any embeddable URLs in this liveupdate.

    Return the newly altered liveupdate for convenience.
    Note: This should be used in async contexts only.

    """
    if isinstance(liveupdate_id, basestring):
        liveupdate_id = uuid.UUID(liveupdate_id)

    try:
        event = LiveUpdateEvent._byID(event_id)
        liveupdate = LiveUpdateStream.get_update(event, liveupdate_id)
    except tdb_cassandra.NotFound:
        g.log.warning("Couldn't find event/liveupdate for embedding: %r / %r",
                      event_id, liveupdate_id)
        return

    urls = _extract_isolated_urls(liveupdate.body)
    liveupdate.media_objects = _scrape_media_objects(urls, maxwidth=maxwidth)
    LiveUpdateStream.add_update(event, liveupdate)

    return liveupdate


def _extract_isolated_urls(md):
    """Extract URLs that exist on their own lines in given markdown.

    This style borrowed from wordpress, which is nice because it's tolerant to
    failures and is easy to understand. See https://codex.wordpress.org/Embeds

    """
    urls = []
    for line in md.splitlines():
        url = sanitize_url(line, require_scheme=True)
        if url and url != "self":
            urls.append(url)
    return urls


def _scrape_media_objects(urls, autoplay=False, maxwidth=_EMBED_WIDTH, max_urls=3):
    """Given a list of URLs, scrape and return the valid media objects."""
    return filter(None, (_scrape_media_object(url,
                                              autoplay=autoplay,
                                              maxwidth=maxwidth)
                         for url in urls[:max_urls]))


def _scrape_media_object(url, autoplay=False, maxwidth=_EMBED_WIDTH):
    """Generate a single media object by URL. Returns None on failure."""
    scraper = LiveScraper.for_url(url, autoplay=autoplay, maxwidth=maxwidth)

    try:
        thumbnail, media_object, secure_media_object = scraper.scrape()
    except (HTTPError, URLError):
        g.log.info("Unable to scrape suspected scrapable URL: %r", url)
        return None

    # No oembed? We don't want it for liveupdate.
    if not media_object or 'oembed' not in media_object:
        return None

    # Use our exact passed URL to ensure matching in markdown.
    # Some scrapers will canonicalize a URL to something we
    # haven't seen yet.
    media_object['oembed']['url'] = url

    return media_object


class LiveScraper(Scraper):
    """The interface to Scraper to be used within liveupdate for media embeds.

    Has support for scrapers that we don't necessarily want to be visible in
    reddit core (like twitter, for example). Outside of the hook system
    so that this functionality is not live for all uses of Scraper proper.

    """

    @classmethod
    def for_url(cls, url, autoplay=False, maxwidth=_EMBED_WIDTH):
        if (_TwitterScraper.matches(url)):
            return _TwitterScraper(url, maxwidth=maxwidth)

        scraper = super(LiveScraper, cls).for_url(
            url, autoplay=autoplay, maxwidth=maxwidth)

        return _EmbedlyCardFallbackScraper(url, scraper)



class _EmbedlyCardFallbackScraper(Scraper):
    def __init__(self, url, scraper):
        self.url = url
        self.scraper = scraper

    def scrape(self):
        thumb, media_object, secure_media_object = self.scraper.scrape()

        # ok, the upstream scraper failed so let's make an embedly card
        if not media_object:
            media_object = secure_media_object = {
                "type": "embedly-card",
                "oembed": {
                    "width": _EMBED_WIDTH,
                    "height": 0,
                    "html": pages.EmbedlyCard(self.url).render(style="html"),
                },
            }

        return thumb, media_object, secure_media_object

    @classmethod
    def media_embed(cls, media_object):
        oembed = media_object["oembed"]

        return MediaEmbed(
            width=oembed["width"],
            height=oembed["height"],
            content=oembed["html"],
        )


class _TwitterScraper(Scraper):
    OEMBED_ENDPOINT = "https://api.twitter.com/1/statuses/oembed.json"
    URL_MATCH = re.compile(r"""https?:
                               //(www\.)?twitter\.com
                               /\w{1,20}
                               /status(es)?
                               /\d+
                            """, re.X)

    def __init__(self, url, maxwidth, omit_script=False):
        self.url = url
        self.maxwidth = maxwidth
        self.omit_script = False

    @classmethod
    def matches(cls, url):
        return cls.URL_MATCH.match(url)

    def _fetch_from_twitter(self):
        params = {
            "url": self.url,
            "format": "json",
            "maxwidth": self.maxwidth,
            "omit_script": self.omit_script,
        }

        content = requests.get(self.OEMBED_ENDPOINT, params=params).content
        return json.loads(content)

    def _make_media_object(self, oembed):
        if oembed.get("type") in ("video", "rich"):
            return {
                "type": "twitter.com",
                "oembed": oembed,
            }
        return None

    def scrape(self):
        oembed = self._fetch_from_twitter()
        if not oembed:
            return None, None, None

        media_object = self._make_media_object(oembed)

        return (
            None,  # no thumbnails for twitter
            media_object,
            media_object,  # Twitter's response is ssl ready by default
        )

    @classmethod
    def media_embed(cls, media_object):
        oembed = media_object["oembed"]

        html = oembed.get("html")
        width = oembed.get("width")

        # Right now Twitter returns no height, so we get ''.
        # We'll reset the height with JS dynamically, but if they support
        # height in the future, this should work transparently.
        height = oembed.get("height") or 0

        if not html and width:
            return

        return MediaEmbed(
            width=width,
            height=height,
            content=html,
        )


def process_liveupdate_scraper_q():
    @g.stats.amqp_processor('liveupdate_scraper_q')
    def _handle_q(msg):
        d = json.loads(msg.body)
        liveupdate = parse_embeds(d['event_id'], d['liveupdate_id'])

        if not liveupdate.media_objects:
            return

        payload = {
            "liveupdate_id": "LiveUpdate_" + d['liveupdate_id'],
            "media_embeds": liveupdate.embeds
        }
        send_event_broadcast(d['event_id'],
                             type="embeds_ready",
                             payload=payload)

    amqp.consume_items('liveupdate_scraper_q', _handle_q, verbose=False)
