import collections
import datetime
import urllib

import pytz

from pylons import c, g
from pylons.i18n import _, ungettext

from r2.lib import filters
from r2.lib.pages import (
    Reddit,
    UserTableItem,
    MediaEmbedBody,
    ModeratorPermissions,
)
from r2.lib.menus import NavMenu, NavButton
from r2.lib.template_helpers import add_sr
from r2.lib.memoize import memoize
from r2.lib.wrapped import Templated, Wrapped
from r2.models import Account, Subreddit, Link, NotFound, Listing, UserListing
from r2.lib.strings import strings
from r2.lib.utils import tup
from r2.lib.jsontemplates import (
    JsonTemplate,
    ObjectTemplate,
    ThingJsonTemplate,
)

from reddit_liveupdate.permissions import ContributorPermissionSet
from reddit_liveupdate.utils import pretty_time, pairwise


class LiveUpdatePage(Reddit):
    extension_handling = False
    extra_stylesheets = Reddit.extra_stylesheets + ["liveupdate.less"]

    def __init__(self, content, websocket_url=None, **kwargs):
        timezone = pytz.timezone(c.liveupdate_event.timezone)
        localized_now = datetime.datetime.now(pytz.UTC).astimezone(timezone)
        utc_offset = localized_now.utcoffset()

        extra_js_config = {
            "liveupdate_event": c.liveupdate_event._id,
            "liveupdate_pixel_domain": g.liveupdate_pixel_domain,
            "liveupdate_permissions": c.liveupdate_permissions,
            "liveupdate_utc_offset": utc_offset.total_seconds() // 60,
            "media_domain": g.media_domain,
        }

        if websocket_url:
            extra_js_config["liveupdate_websocket"] = websocket_url

        title = c.liveupdate_event.title
        if c.liveupdate_event.state == "live":
            title = _("[live]") + " " + title

        Reddit.__init__(self,
            title=title,
            show_sidebar=False,
            content=content,
            extra_js_config=extra_js_config,
            **kwargs
        )

    def build_toolbars(self):
        toolbars = []

        if c.liveupdate_permissions:
            tabs = [
                NavButton(
                    _("updates"),
                    "/",
                ),
            ]

            if c.liveupdate_permissions.allow("settings"):
                tabs.append(NavButton(
                    _("settings"),
                    "/edit",
                ))

            if c.liveupdate_permissions.allow("manage"):
                tabs.append(NavButton(
                    _("contributors"),
                    "/contributors",
                ))

            toolbars.append(NavMenu(
                tabs,
                base_path="/live/" + c.liveupdate_event._id,
                type="tabmenu",
            ))

        return toolbars


class LiveUpdateEmbed(LiveUpdatePage):
    extra_page_classes = ["embed"]


class LiveUpdateEventJsonTemplate(ThingJsonTemplate):
    _data_attrs_ = ThingJsonTemplate.data_attrs(
        id="_id",
        state="state",
        viewer_count="viewer_count",
        viewer_count_fuzzed="viewer_count_fuzzed",
        title="title",
        description="description",
        description_html="description_html",
    )

    def thing_attr(self, thing, attr):
        if attr == "_fullname":
            return "LiveUpdateEvent_" + thing._id
        elif attr == "viewer_count":
            return thing.active_visitors
        elif attr == "viewer_count_fuzzed":
            return thing.active_visitors_fuzzed
        elif attr == "description_html":
            return filters.spaceCompress(
                filters.safemarkdown(thing.description) or "")
        else:
            return ThingJsonTemplate.thing_attr(self, thing, attr)

    def kind(self, wrapped):
        return "LiveUpdateEvent"


class LiveUpdateEventPage(Templated):
    def __init__(self, event, listing, show_sidebar):
        self.event = event
        self.listing = listing
        if show_sidebar:
            self.discussions = LiveUpdateOtherDiscussions()
        self.show_sidebar = show_sidebar

        contributor_accounts = Account._byID(event.contributors.keys(),
                                             data=True, return_dict=False)
        self.contributors = sorted((LiveUpdateAccount(e)
                                   for e in contributor_accounts),
                                   key=lambda e: e.name)

        Templated.__init__(self)


class LiveUpdateEventConfiguration(Templated):
    def __init__(self):
        self.ungrouped_timezones = []
        self.grouped_timezones = collections.defaultdict(list)

        for tzname in pytz.common_timezones:
            if "/" not in tzname:
                self.ungrouped_timezones.append(tzname)
            else:
                region, zone = tzname.split("/", 1)
                self.grouped_timezones[region].append(zone)

        Templated.__init__(self)


class LiveUpdateContributorPermissions(ModeratorPermissions):
    def __init__(self, account, permissions, embedded=False):
        ModeratorPermissions.__init__(
            self,
            user=account,
            permissions_type=ContributorTableItem.type,
            permissions=permissions,
            editable=True,
            embedded=embedded,
        )


class ContributorTableItem(UserTableItem):
    type = "liveupdate_contributor"

    def __init__(self, contributor, event, editable):
        self.event = event
        self.render_class = ContributorTableItem
        self.permissions = LiveUpdateContributorPermissions(
            contributor.account, contributor.permissions)
        UserTableItem.__init__(self, contributor.account, editable=editable)

    @property
    def cells(self):
        if self.editable:
            return ("user", "sendmessage", "remove", "permissions",
                    "permissionsctl")
        else:
            return ("user",)

    @property
    def _id(self):
        return self.user._id

    @classmethod
    def add_props(cls, item, *k):
        return item

    @property
    def container_name(self):
        return self.event._id

    @property
    def remove_action(self):
        return "live/%s/rm_contributor" % self.event._id


class ContributorListing(UserListing):
    type = "liveupdate_contributor"
    permissions_form = LiveUpdateContributorPermissions(
        account=None,
        permissions=ContributorPermissionSet.SUPERUSER,
        embedded=True,
    )

    def __init__(self, event, builder, editable=True):
        self.event = event
        UserListing.__init__(self, builder, addable=editable, nextprev=False)

    @property
    def destination(self):
        return "live/%s/add_contributor" % self.event._id

    @property
    def form_title(self):
        return _("add contributor")

    @property
    def title(self):
        return _("current contributors")

    @property
    def container_name(self):
        return self.event._id


class LinkBackToLiveUpdate(Templated):
    pass


class LiveUpdateEventPageJsonTemplate(JsonTemplate):
    def render(self, thing=None, *a, **kwargs):
        return ObjectTemplate(thing.listing.render() if thing else {})


class LiveUpdateJsonTemplate(ThingJsonTemplate):
    _data_attrs_ = ThingJsonTemplate.data_attrs(
        id="_id",
        body="body",
        body_html="body_html",
        author="author",
        stricken="stricken",
        embeds="embeds",
    )

    def thing_attr(self, thing, attr):
        if attr == "_id":
            return str(thing._id)
        elif attr == "body_html":
            return filters.spaceCompress(filters.safemarkdown(thing.body))
        elif attr == "author":
            if not thing.author.deleted:
                return thing.author.name
            else:
                return None
        elif attr == "stricken":
            return bool(thing.stricken)
        return ThingJsonTemplate.thing_attr(self, thing, attr)

    def kind(self, wrapped):
        return "LiveUpdate"


class LiveUpdateAccount(Templated):
    def __init__(self, user):
        Templated.__init__(self,
            deleted=user._deleted,
            name=user.name,
            fullname=user._fullname,
        )


class LiveUpdateOtherDiscussions(Templated):
    max_links = 5

    def __init__(self):
        links = self.get_links(c.liveupdate_event._id)
        self.more_links = len(links) > self.max_links
        self.links = links[:self.max_links]
        self.submit_url = "/submit?" + urllib.urlencode({
            "url": add_sr("/live/" + c.liveupdate_event._id,
                          sr_path=False, force_hostname=True),
            "title": c.liveupdate_event.title.encode("utf-8"),
        })

        Templated.__init__(self)

    @classmethod
    @memoize("live_update_discussion_ids", time=60)
    def _get_related_link_ids(cls, event_id):
        url = add_sr("/live/%s" % event_id, sr_path=False, force_hostname=True)

        try:
            links = tup(Link._by_url(url, sr=None))
        except NotFound:
            links = []

        return [link._id for link in links]

    @classmethod
    def get_links(cls, event_id):
        link_ids = cls._get_related_link_ids(event_id)
        links = Link._byID(link_ids, data=True, return_dict=False)
        links.sort(key=lambda L: L.num_comments, reverse=True)

        sr_ids = set(L.sr_id for L in links)
        subreddits = Subreddit._byID(sr_ids, data=True)

        wrapped = []
        for link in links:
            w = Wrapped(link)

            w.subreddit = subreddits[link.sr_id]

            # ideally we'd check if the user can see the subreddit, but by
            # doing this we keep everything user unspecific which makes caching
            # easier.
            if w.subreddit.type == "private":
                continue

            comment_label = ungettext("comment", "comments", link.num_comments)
            w.comments_label = strings.number_label % dict(
                num=link.num_comments, thing=comment_label)

            wrapped.append(w)
        return wrapped


class LiveUpdateSeparator(Templated):
    def __init__(self, older):
        self.date = older.replace(minute=0, second=0, microsecond=0)
        self.date_str = pretty_time(self.date, allow_relative=False)
        Templated.__init__(self)


class LiveUpdateListing(Listing):
    def things_with_separators(self):
        if self.things:
            yield self.things[0]

        for newer, older in pairwise(self.things):
            if newer._date.hour != older._date.hour:
                yield LiveUpdateSeparator(older._date)
            yield older


class LiveUpdateMediaEmbedBody(MediaEmbedBody):
    pass


def liveupdate_add_props(user, wrapped):
    account_ids = set(w.author_id for w in wrapped)
    accounts = Account._byID(account_ids, data=True)

    for item in wrapped:
        item.author = LiveUpdateAccount(accounts[item.author_id])

        item.date_str = pretty_time(item._date)
