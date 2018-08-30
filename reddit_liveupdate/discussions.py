import itertools

from pylons import app_globals as g

from r2.lib.memoize import memoize
from r2.models import Link, NotFound, IDBuilder, Subreddit


MAX_LINK_IDS_TO_CACHE = 50


@memoize("live_update_discussion_fullnames", time=60)
def _get_related_link_ids(event_id):
    # imported here to avoid circular import
    from reddit_liveupdate.pages import make_event_url

    url = make_event_url(event_id)

    try:
        links = Link._by_url(url, sr=None)
    except NotFound:
        links = []

    links = itertools.islice(links, MAX_LINK_IDS_TO_CACHE)
    return [link._fullname for link in links]


def get_discussions(event, limit, show_hidden=False):
    """Return a builder providing Links that point at the given live thread."""

    hidden_links = event.hidden_discussions
    def _keep_discussion_link(link):
        if link._spam or link._deleted:
            return False

        # just don't allow any private subreddits so we don't get into a
        # situation where an abusive link is posted in a private subreddit and
        # contributors can't do anything about it because they can't see it.
        if link.subreddit_slow.type in Subreddit.private_types:
            return False

        if not link.subreddit_slow.discoverable:
            return False

        if link._score < g.liveupdate_min_score_for_discussions:
            return False

        link.is_hidden_discussion = link._id in hidden_links
        if not show_hidden and link.is_hidden_discussion:
            return False

        return True

    link_fullnames = _get_related_link_ids(event._id)
    link_fullnames = link_fullnames[:limit]
    return IDBuilder(
        query=link_fullnames,
        skip=True,
        keep_fn=_keep_discussion_link,
    )
