import collections
import urllib

from pylons import tmpl_context as c
from pylons import app_globals as g
from pylons.i18n import _, N_

from r2.lib import filters, websockets
from r2.lib.pages import (
    Reddit,
    UserTableItem,
    MediaEmbedBody,
    ModeratorPermissions,
    MAX_DESCRIPTION_LENGTH,
)
from r2.lib.menus import NavMenu, NavButton
from r2.lib.template_helpers import add_sr
from r2.lib.wrapped import Templated, Wrapped
from r2.models import Account, Listing, UserListing
from r2.lib.template_helpers import static
from r2.lib.utils import trunc_string
from r2.lib.jsontemplates import (
    JsonTemplate,
    ObjectTemplate,
    ThingJsonTemplate,
    UserTableItemJsonTemplate,
)

from reddit_liveupdate.discussions import get_discussions
from reddit_liveupdate.permissions import ContributorPermissionSet
from reddit_liveupdate.utils import pretty_time


def make_event_url(event_id):
    return add_sr("/live/%s/" % event_id, sr_path=False, force_hostname=True)


class LiveUpdatePage(Reddit):
    extra_stylesheets = Reddit.extra_stylesheets + ["liveupdate.less"]

    def __init__(self, title, content, **kwargs):
        Reddit.__init__(self,
            title=title,
            show_sidebar=False,
            show_newsletterbar=False,
            content=content,
            **kwargs
        )

    def build_toolbars(self):
        return []


class LiveUpdateMetaPage(LiveUpdatePage):
    def build_toolbars(self):
        tabs = [
            NavButton(
                _("reddit live"),
                "/",
            ),
            NavButton(
                _("happening now"),
                "/happening_now",
            ),
        ]

        if c.user_is_loggedin:
            tabs.extend((
                NavButton(
                    _("my live threads"),
                    "/mine",
                ),
            ))

        if c.user_is_loggedin and c.user.employee:
            tabs.extend([
                NavButton(
                    _("active"),
                    "/active",
                ),
                NavButton(
                    _("live"),
                    "/open",
                ),
                NavButton(
                    _("closed"),
                    "/closed",
                ),
            ])

            if c.user_is_admin:
                tabs.extend([
                    NavButton(
                        _("reported"),
                        "/reported",
                    ),
                ])

        return [NavMenu(
            tabs,
            base_path="/live/",
            type="tabmenu",
        )]


class LiveUpdateEventPage(LiveUpdatePage):
    extension_handling = False

    def __init__(self, content, **kwargs):
        extra_js_config = {
            "liveupdate_event": c.liveupdate_event._id,
            "liveupdate_pixel_domain": g.liveupdate_pixel_domain,
            "liveupdate_permissions": c.liveupdate_permissions,
            "media_domain": g.media_domain,
        }

        title = c.liveupdate_event.title
        if c.liveupdate_event.state == "live":
            title = _("[live]") + " " + title

        LiveUpdatePage.__init__(self,
            title=title,
            content=content,
            extra_js_config=extra_js_config,
            **kwargs
        )

    def build_toolbars(self):
        tabs = [
            NavButton(
                _("updates"),
                "/",
            ),
            NavButton(
                _("discussions"),
                "/discussions",
            ),
        ]

        if c.liveupdate_permissions:
            if (c.liveupdate_permissions.allow("settings") or
                    c.liveupdate_permissions.allow("close")):
                tabs.append(NavButton(
                    _("settings"),
                    "/edit",
                ))

            # all contributors should see this so they can leave if they want
            tabs.append(NavButton(
                _("contributors"),
                "/contributors",
            ))

        return [
            NavMenu(
                tabs,
                base_path="/live/" + c.liveupdate_event._id,
                type="tabmenu",
            ),
        ]


class LiveUpdateEventAppPage(LiveUpdateEventPage):
    def __init__(self, **kwargs):
        description = (c.liveupdate_event.description or
            _("real-time updates on %(short_description)s") %
               dict(short_description=g.short_description))

        og_data = {
            "type": "article",
            "url": make_event_url(c.liveupdate_event._id),
            "description": description,
            "image": static("liveupdate-logo.png"),
            "image:width": "300",
            "image:height": "300",
            "site_name": "reddit",
            "ttl": "600",  # have this stuff re-fetched frequently
        }

        LiveUpdateEventPage.__init__(
            self,
            og_data=og_data,
            short_description=description,
            **kwargs
        )


class LiveUpdateEventFocusPage(LiveUpdateEventPage):
    def __init__(self, focused_update, **kwargs):
        og_data = {
            "type": "article",
            "url": make_event_url(c.liveupdate_event._id),
            "description": trunc_string(
                focused_update.body.strip(), MAX_DESCRIPTION_LENGTH),
            "image": static("liveupdate-logo.png"),
            "image:width": "300",
            "image:height": "300",
            "site_name": "reddit",
        }

        LiveUpdateEventPage.__init__(
            self,
            og_data=og_data,
            **kwargs
        )

    def build_toolbars(self):
        return []


class LiveUpdateEventEmbed(LiveUpdateEventPage):
    extra_page_classes = ["embed"]

    def __init__(self, *args, **kwargs):
        self.base_url = add_sr(
            "/live/" + c.liveupdate_event._id,
            force_hostname=True,
            force_https=c.secure,
        )
        super(LiveUpdateEventEmbed, self).__init__(*args, **kwargs)


class LiveUpdateEventJsonTemplate(ThingJsonTemplate):
    _data_attrs_ = ThingJsonTemplate.data_attrs(
        id="_id",
        state="state",
        viewer_count="viewer_count",
        viewer_count_fuzzed="viewer_count_fuzzed",
        total_views="total_views",
        title="title",
        nsfw="nsfw",
        description="description",
        description_html="description_html",
        resources="resources",
        resources_html="resources_html",
        websocket_url="websocket_url",
        is_announcement="is_announcement",
        announcement_url="announcement_url",
        button_cta="button_cta",
        icon="icon",
    )

    def thing_attr(self, thing, attr):
        if attr == "_fullname":
            return "LiveUpdateEvent_" + thing._id
        elif attr == "viewer_count":
            if thing.state == "live":
                return thing.active_visitors
            else:
                return None
        elif attr == "viewer_count_fuzzed":
            if thing.state == "live":
                return thing.active_visitors_fuzzed
            else:
                return None
        elif attr == "total_views":
            # this requires an extra query, so we'll only show it in places
            # where we're just getting one event.
            if not hasattr(thing, "total_views"):
                return None
            return thing.total_views
        elif attr == "description_html":
            return filters.spaceCompress(
                filters.safemarkdown(thing.description, nofollow=True) or "")
        elif attr == "resources_html":
            return filters.spaceCompress(
                filters.safemarkdown(thing.resources, nofollow=True) or "")
        elif attr == "websocket_url":
            if thing.state == "live":
                return websockets.make_url(
                    "/live/" + thing._id, max_age=24 * 60 * 60)
            else:
                return None
        else:
            return ThingJsonTemplate.thing_attr(self, thing, attr)

    def kind(self, wrapped):
        return "LiveUpdateEvent"


class LiveAnnouncementsJsonTemplate(LiveUpdateEventJsonTemplate):
    _data_attrs_ = LiveUpdateEventJsonTemplate.data_attrs(
        is_announcement="is_announcement",
        announcement_url="announcement_url",
        button_cta="button_cta",
        icon="icon",
    )

    def thing_attr(self, thing, attr):
        if attr == "is_announcement":
            return bool(thing.is_announcement)
        elif attr == "announcement_url":
            return str(thing.announcement_url)
        elif attr == "button_cta":
            return str(thing.button_cta)
        elif attr == "icon":
            return str(thing.icon)
        return LiveUpdateEventJsonTemplate.thing_attr(self, thing, attr)


class LiveUpdateFeaturedEventJsonTemplate(LiveUpdateEventJsonTemplate):
    _data_attrs_ = LiveUpdateEventJsonTemplate.data_attrs(
        featured_in="featured_in",
    )

    def thing_attr(self, thing, attr):
        if attr == "featured_in":
            return list(thing.featured_in)
        return LiveUpdateEventJsonTemplate.thing_attr(self, thing, attr)


REPORT_TYPES = collections.OrderedDict((
    ("spam", N_("spam")),
    ("vote-manipulation", N_("vote manipulation")),
    ("personal-information", N_("personal information")),
    ("sexualizing-minors", N_("sexualizing minors")),
    ("site-breaking", N_("breaking reddit")),
))


class LiveUpdateEventApp(Templated):
    def __init__(self, event, listing, show_sidebar, report_type):
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

        self.report_types = REPORT_TYPES
        self.report_type = report_type

        Templated.__init__(self)


class LiveUpdateFocusApp(Templated):
    pass


class LiveUpdateEventConfiguration(Templated):
    pass


class LiveUpdateContributorPermissions(ModeratorPermissions):
    def __init__(self, permissions_type, account, permissions, embedded=False):
        ModeratorPermissions.__init__(
            self,
            user=account,
            permissions_type=permissions_type,
            permissions=permissions,
            editable=True,
            embedded=embedded,
        )


class LiveUpdateContributorTableItem(UserTableItem):
    type = "liveupdate_contributor"

    def __init__(self, contributor, event, editable):
        self.event = event
        self.render_class = LiveUpdateContributorTableItem
        self.permissions = LiveUpdateContributorPermissions(
            self.type, contributor.account, contributor.permissions)
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


class InvitedLiveUpdateContributorTableItem(LiveUpdateContributorTableItem):
    type = "liveupdate_contributor_invite"

    @property
    def remove_action(self):
        return "live/%s/rm_contributor_invite" % self.event._id


class ContributorTableItemJsonTemplate(UserTableItemJsonTemplate):
    _data_attrs_ = UserTableItemJsonTemplate.data_attrs(
        permissions="permissions",
    )

    def thing_attr(self, thing, attr):
        if attr == "permissions":
            return [perm for perm, has in
                thing.permissions.permissions.iteritems() if has]
        else:
            return UserTableItemJsonTemplate.thing_attr(self, thing, attr)


class LiveUpdateInvitedContributorListing(UserListing):
    type = "liveupdate_contributor_invite"

    permissions_form = LiveUpdateContributorPermissions(
        permissions_type="liveupdate_contributor_invite",
        account=None,
        permissions=ContributorPermissionSet.SUPERUSER,
        embedded=True,
    )

    def __init__(self, event, builder, editable=False):
        self.event = event
        UserListing.__init__(self, builder, addable=editable, nextprev=False)

    @property
    def container_name(self):
        return self.event._id

    @property
    def destination(self):
        return "live/%s/invite_contributor" % self.event._id

    @property
    def form_title(self):
        return _("invite contributor")

    @property
    def title(self):
        return _("invited contributors")


class LiveUpdateContributorListing(LiveUpdateInvitedContributorListing):
    type = "liveupdate_contributor"

    def __init__(self, event, builder, has_invite, is_contributor):
        self.has_invite = has_invite
        self.is_contributor = is_contributor
        super(LiveUpdateContributorListing, self).__init__(
            event, builder, editable=False)

    @property
    def title(self):
        return _("current contributors")


class LinkBackToLiveUpdate(Templated):
    pass


class LiveUpdateEventAppJsonTemplate(JsonTemplate):
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
        mobile_embeds="mobile_embeds",
    )

    def thing_attr(self, thing, attr):
        if attr == "_id":
            return str(thing._id)
        elif attr == "body_html":
            return filters.spaceCompress(filters.safemarkdown(thing.body, nofollow=True))
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


def make_submit_url(event):
    return "/submit?" + urllib.urlencode({
        "url": make_event_url(event._id),
        "title": event.title.encode("utf-8"),
    })


class LiveUpdateOtherDiscussions(Templated):
    max_links = 5

    def __init__(self):
        builder = get_discussions(c.liveupdate_event, limit=self.max_links+1)
        links, prev, next, bcount, acount = builder.get_items()

        self.more_links = len(links) > self.max_links
        self.links = links[:self.max_links]
        self.submit_url = make_submit_url(c.liveupdate_event)

        Templated.__init__(self)


class LiveUpdateDiscussionsListing(Templated):
    pass


class LiveUpdateListing(Listing):
    pass


class LiveUpdateReportedEventListing(Listing):
    def __init__(self, *args, **kwargs):
        self.report_types = REPORT_TYPES
        Listing.__init__(self, *args, **kwargs)


class LiveUpdateMediaEmbedBody(MediaEmbedBody):
    pass


class LiveUpdateReportedEventRow(Wrapped):
    @property
    def report_counts(self):
        for report_type in REPORT_TYPES:
            yield self.reports_by_type[report_type]


class LiveUpdateFeaturedEvent(Wrapped):
    pass


def liveupdate_add_props(user, wrapped):
    account_ids = set(w.author_id for w in wrapped)
    accounts = Account._byID(account_ids, data=True)

    for item in wrapped:
        item.author = LiveUpdateAccount(accounts[item.author_id])

        item.date_str = pretty_time(item._date)


class LiveUpdateCreate(Templated):
    pass


class LiveAnnouncementsCreate(Templated):
    pass

class EmbedlyCard(Templated):
    def __init__(self, url):
        self.url = url
        Templated.__init__(self)


class LiveUpdateHome(Templated):
    pass


class LiveUpdateNSFWEmbed(Templated):
    pass


class LiveUpdateAnnouncementsBar(Templated):
    def __init__(self, event, enable_logo=True):
        self.event = event
        self.enable_logo = enable_logo
        Templated.__init__(self)


class LiveUpdateHappeningNowBar(Templated):
    def __init__(self, event, enable_logo=True):
        self.event = event
        self.enable_logo = enable_logo
        Templated.__init__(self)


class AnnouncementsAdmin(Templated):
    """Admin page for choosing the promoted announcement."""

    def __init__(self, featured_events):
        if featured_events:
            target, event = featured_events.items()[0]
            super(AnnouncementsAdmin, self).__init__(
                featured_event=LiveUpdateAnnouncementsBar(event, enable_logo=False),
                target=target,
            )
        else:
            super(AnnouncementsAdmin, self).__init__(
                featured_event=None,
                target=None,
            )


class HappeningNowAdmin(Templated):
    """Admin page for choosing the promoted reddit live thread."""

    def __init__(self, featured_events):
        if featured_events:
            target, event = featured_events.items()[0]
            super(HappeningNowAdmin, self).__init__(
                featured_event=LiveUpdateHappeningNowBar(event, enable_logo=False),
                target=target,
            )
        else:
            super(HappeningNowAdmin, self).__init__(
                featured_event=None,
                target=None,
            )
