import collections
import hashlib
import os

from pylons import g, c, request, response
from pylons.i18n import _

from r2.config.extensions import is_api
from r2.controllers import add_controller
from r2.controllers.reddit_base import (
    MinimalController,
    RedditController,
    base_listing,
)
from r2.lib import websockets
from r2.lib.base import BaseController, abort
from r2.lib.db import tdb_cassandra
from r2.lib.filters import safemarkdown
from r2.lib.validator import (
    validate,
    validatedForm,
    VAdmin,
    VEmployee,
    VBoolean,
    VByName,
    VCount,
    VExistingUname,
    VLimit,
    VMarkdown,
    VModhash,
    VRatelimit,
    VOneOf,
    VInt,
    VUser,
)
from r2.models import (
    Account,
    IDBuilder,
    LinkListing,
    Listing,
    NotFound,
    QueryBuilder,
    SimpleBuilder,
    Subreddit,
)
from r2.models.admintools import send_system_message
from r2.lib.errors import errors
from r2.lib.utils import url_links_builder
from r2.lib.pages import PaneStack, Wrapped, RedditError

from reddit_liveupdate import pages, queries
from reddit_liveupdate.media_embeds import (
    get_live_media_embed,
    queue_parse_embeds,
)
from reddit_liveupdate.models import (
    InviteNotFoundError,
    LiveUpdate,
    LiveUpdateEvent,
    LiveUpdateStream,
    LiveUpdateContributorInvitesByEvent,
    LiveUpdateReportsByAccount,
    LiveUpdateReportsByEvent,
    ActiveVisitorsByLiveUpdateEvent,
)
from reddit_liveupdate.permissions import ContributorPermissionSet
from reddit_liveupdate.utils import send_event_broadcast
from reddit_liveupdate.validators import (
    is_event_configuration_valid,
    EVENT_CONFIGURATION_VALIDATORS,
    VLiveUpdate,
    VLiveUpdateContributorWithPermission,
    VLiveUpdateEvent,
    VLiveUpdatePermissions,
    VLiveUpdateID,
)


INVITE_MESSAGE = """\
**oh my! you are invited to become a contributor to [%(title)s](%(url)s)**.

*to accept* visit the [contributors page for the stream](%(url)s/contributors)
and click "accept".

*otherwise,* if you did not expect to receive this, you can simply ignore this
invitation or report it.
"""
REPORTED_MESSAGE = """\
The live update stream [%(title)s](%(url)s) was just reported for %(reason)s.
Please see the [reports page](/live/reported) for more information.
"""


def _broadcast(type, payload):
    send_event_broadcast(c.liveupdate_event._id, type, payload)


class LiveUpdateBuilder(QueryBuilder):
    def wrap_items(self, items):
        wrapped = []
        for item in items:
            w = self.wrap(item)
            wrapped.append(w)
        pages.liveupdate_add_props(c.user, wrapped)
        return wrapped

    def keep_item(self, item):
        return not item.deleted


class LiveUpdateContributor(object):
    def __init__(self, account, permissions):
        self.account = account
        self.permissions = permissions

    @property
    def _id(self):
        return self.account._id


class LiveUpdateContributorBuilder(SimpleBuilder):
    def __init__(self, event, perms_by_contributor, editable):
        self.event = event
        self.editable = editable

        contributor_accounts = Account._byID(
            perms_by_contributor.keys(), data=True)
        contributors = [
            LiveUpdateContributor(account, perms_by_contributor[account._id])
            for account in contributor_accounts.itervalues()]
        contributors.sort(key=lambda r: r.account.name)

        SimpleBuilder.__init__(
            self,
            contributors,
            keep_fn=self.keep_item,
            wrap=self.wrap_item,
            skip=False,
            num=0,
        )

    def keep_item(self, item):
        return not item.account._deleted

    def wrap_item(self, item):
        return pages.ContributorTableItem(
            item,
            self.event,
            editable=self.editable,
        )

    def wrap_items(self, items):
        wrapped = []
        for item in items:
            wrapped.append(self.wrap_item(item))
        return wrapped


class LiveUpdateInvitedContributorBuilder(LiveUpdateContributorBuilder):
    def wrap_item(self, item):
        return pages.InvitedContributorTableItem(
            item,
            self.event,
            editable=self.editable,
        )


@add_controller
class LiveUpdatePixelController(BaseController):
    def __init__(self, *args, **kwargs):
        self._pixel_data = None
        BaseController.__init__(self, *args, **kwargs)

    @property
    def _pixel_contents(self):
        if not self._pixel_data:
            with open(os.path.join(g.paths["root"],
                                   "public/static/pixel.png")) as f:
                self._pixel_data = f.read()
        return self._pixel_data

    def GET_pixel(self, event):
        extension = request.environ.get("extension")
        if extension != "png":
            abort(404)

        event_id = event[:50]  # some very simple poor-man's validation
        user_agent = request.user_agent or ''
        user_id = hashlib.sha1(request.ip + user_agent).hexdigest()
        ActiveVisitorsByLiveUpdateEvent.touch(event_id, user_id)

        response.content_type = "image/png"
        response.headers["Cache-Control"] = "no-cache, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
        return self._pixel_contents


@add_controller
class LiveUpdateController(RedditController):
    def __before__(self, event):
        RedditController.__before__(self)

        if event:
            try:
                c.liveupdate_event = LiveUpdateEvent._byID(event)
            except tdb_cassandra.NotFound:
                pass

        if not c.liveupdate_event:
            self.abort404()

        if c.liveupdate_event.banned and not c.user_is_admin:
            error_page = RedditError(
                title=_("this stream has been banned"),
                message="",
                image="subreddit-banned.png",
            )
            request.environ["usable_error_content"] = error_page.render()
            self.abort403()

        if c.user_is_loggedin:
            c.liveupdate_permissions = \
                    c.liveupdate_event.get_permissions(c.user)

            # revoke some permissions from everyone after closing
            if c.liveupdate_event.state != "live":
                c.liveupdate_permissions = (c.liveupdate_permissions
                    .without("update")
                    .without("close")
                )

            if c.user_is_admin:
                c.liveupdate_permissions = ContributorPermissionSet.SUPERUSER
        else:
            c.liveupdate_permissions = ContributorPermissionSet.NONE

    @validate(
        num=VLimit("limit", default=25, max_limit=100),
        after=VLiveUpdateID("after"),
        before=VLiveUpdateID("before"),
        count=VCount("count"),
        is_embed=VBoolean("is_embed"),
    )
    def GET_listing(self, num, after, before, count, is_embed):
        reverse = False
        if before:
            reverse = True
            after = before

        query = LiveUpdateStream.query([c.liveupdate_event._id],
                                       count=num, reverse=reverse)
        if after:
            query.column_start = after
        builder = LiveUpdateBuilder(query=query, skip=True,
                                    reverse=reverse, num=num,
                                    count=count)
        listing = pages.LiveUpdateListing(builder)
        wrapped_listing = listing.listing()

        if c.user_is_loggedin:
            report_type = LiveUpdateReportsByAccount.get_report(
                c.user, c.liveupdate_event)
        else:
            report_type = None

        content = pages.LiveUpdateEventApp(
            event=c.liveupdate_event,
            listing=wrapped_listing,
            show_sidebar=not is_embed,
            report_type=report_type,
        )

        c.js_preload.set_wrapped(
            "/live/" + c.liveupdate_event._id + "/about.json",
            Wrapped(c.liveupdate_event),
        )

        c.js_preload.set_wrapped(
            "/live/" + c.liveupdate_event._id + ".json",
            wrapped_listing,
        )

        # don't generate a url unless this is the main page of an event
        websocket_url = None
        if c.liveupdate_event.state == "live" and not after and not before:
            websocket_url = websockets.make_url(
                "/live/" + c.liveupdate_event._id, max_age=24 * 60 * 60)

        if not is_embed:
            return pages.LiveUpdateEventPage(
                content=content,
                websocket_url=websocket_url,
                page_classes=['liveupdate-app'],
            ).render()
        else:
            # ensure we're off the cookie domain before allowing embedding
            if request.host != g.media_domain:
                abort(404)
            c.allow_framing = True

            return pages.LiveUpdateEventEmbed(
                content=content,
                websocket_url=websocket_url,
                page_classes=['liveupdate-app'],
            ).render()

    def GET_about(self):
        if not is_api():
            self.abort404()
        content = Wrapped(c.liveupdate_event)
        return pages.LiveUpdateEventPage(content=content).render()

    @base_listing
    def GET_discussions(self, num, after, reverse, count):
        builder = url_links_builder(
            url="/live/" + c.liveupdate_event._id,
            num=num,
            after=after,
            reverse=reverse,
            count=count,
        )
        listing = LinkListing(builder).listing()
        return pages.LiveUpdateEventPage(
            content=listing,
        ).render()

    @validate(
        VLiveUpdateContributorWithPermission("settings"),
    )
    def GET_edit(self):
        return pages.LiveUpdateEventPage(
            content=pages.LiveUpdateEventConfiguration(),
        ).render()

    @validatedForm(
        VLiveUpdateContributorWithPermission("settings"),
        VModhash(),
        **EVENT_CONFIGURATION_VALIDATORS
    )
    def POST_edit(self, form, jquery, title, description):
        if not is_event_configuration_valid(form):
            return

        changes = {}
        if title != c.liveupdate_event.title:
            changes["title"] = title
        if description != c.liveupdate_event.description:
            changes["description"] = description
            changes["description_html"] = safemarkdown(description, wrap=False) or ""
        _broadcast(type="settings", payload=changes)

        c.liveupdate_event.title = title
        c.liveupdate_event.description = description
        c.liveupdate_event._commit()

        form.set_html(".status", _("saved"))
        form.refresh()

    # TODO: pass listing params on
    def GET_contributors(self):
        editable = c.liveupdate_permissions.allow("manage")

        content = [pages.LinkBackToLiveUpdate()]

        contributors = c.liveupdate_event.contributors
        invites = LiveUpdateContributorInvitesByEvent.get_all(c.liveupdate_event)

        contributor_builder = LiveUpdateContributorBuilder(
            c.liveupdate_event, contributors, editable)
        contributor_listing = pages.LiveUpdateContributorListing(
            c.liveupdate_event,
            contributor_builder,
            has_invite=c.user_is_loggedin and c.user._id in invites,
            is_contributor=c.user_is_loggedin and c.user._id in contributors,
        ).listing()
        content.append(contributor_listing)

        if editable:
            invite_builder = LiveUpdateInvitedContributorBuilder(
                c.liveupdate_event, invites, editable)
            invite_listing = pages.LiveUpdateInvitedContributorListing(
                c.liveupdate_event,
                invite_builder,
                editable=editable,
            ).listing()
            content.append(invite_listing)

        return pages.LiveUpdateEventPage(
            content=PaneStack(content),
        ).render()

    @validatedForm(
        VLiveUpdateContributorWithPermission("manage"),
        VModhash(),
        user=VExistingUname("name"),
        type_and_perms=VLiveUpdatePermissions("type", "permissions"),
    )
    def POST_invite_contributor(self, form, jquery, user, type_and_perms):
        if form.has_errors("name", errors.USER_DOESNT_EXIST,
                                   errors.NO_USER):
            return
        if form.has_errors("type", errors.INVALID_PERMISSION_TYPE):
            return
        if form.has_errors("permissions", errors.INVALID_PERMISSIONS):
            return

        type, permissions = type_and_perms

        invites = LiveUpdateContributorInvitesByEvent.get_all(c.liveupdate_event)
        if user._id in invites or user._id in c.liveupdate_event.contributors:
            c.errors.add(errors.LIVEUPDATE_ALREADY_CONTRIBUTOR, field="name")
            form.has_errors("name", errors.LIVEUPDATE_ALREADY_CONTRIBUTOR)
            return

        if len(invites) >= g.liveupdate_invite_quota:
            c.errors.add(errors.LIVEUPDATE_TOO_MANY_INVITES, field="name")
            form.has_errors("name", errors.LIVEUPDATE_TOO_MANY_INVITES)
            return

        LiveUpdateContributorInvitesByEvent.create(
            c.liveupdate_event, user, permissions)

        # TODO: make this i18n-friendly when we have such a system for PMs
        send_system_message(
            user,
            subject="invitation to contribute to " + c.liveupdate_event.title,
            body=INVITE_MESSAGE % {
                "title": c.liveupdate_event.title,
                "url": "/live/" + c.liveupdate_event._id,
            },
        )

        # add the user to the table
        contributor = LiveUpdateContributor(user, permissions)
        user_row = pages.InvitedContributorTableItem(
            contributor, c.liveupdate_event, editable=True)
        jquery(".liveupdate_contributor_invite-table").show(
            ).find("table").insert_table_rows(user_row)

    @validatedForm(
        VUser(),
        VModhash(),
    )
    def POST_leave_contributor(self, form, jquery):
        c.liveupdate_event.remove_contributor(c.user)

    @validatedForm(
        VLiveUpdateContributorWithPermission("manage"),
        VModhash(),
        user=VByName("id", thing_cls=Account),
    )
    def POST_rm_contributor_invite(self, form, jquery, user):
        LiveUpdateContributorInvitesByEvent.remove(
            c.liveupdate_event, user)

    @validatedForm(
        VUser(),
        VModhash(),
    )
    def POST_accept_contributor_invite(self, form, jquery):
        try:
            permissions = LiveUpdateContributorInvitesByEvent.get(
                c.liveupdate_event, c.user)
        except InviteNotFoundError:
            c.errors.add(errors.LIVEUPDATE_NO_INVITE_FOUND)
            form.set_error(errors.LIVEUPDATE_NO_INVITE_FOUND, None)
            return

        LiveUpdateContributorInvitesByEvent.remove(
            c.liveupdate_event, c.user)

        c.liveupdate_event.add_contributor(c.user, permissions)
        jquery.refresh()

    @validatedForm(
        VLiveUpdateContributorWithPermission("manage"),
        VModhash(),
        user=VExistingUname("name"),
        type_and_perms=VLiveUpdatePermissions("type", "permissions"),
    )
    def POST_set_contributor_permissions(self, form, jquery, user, type_and_perms):
        if form.has_errors("name", errors.USER_DOESNT_EXIST,
                                   errors.NO_USER):
            return
        if form.has_errors("type", errors.INVALID_PERMISSION_TYPE):
            return
        if form.has_errors("permissions", errors.INVALID_PERMISSIONS):
            return

        type, permissions = type_and_perms
        if type == "liveupdate_contributor":
            c.liveupdate_event.update_contributor_permissions(user, permissions)
        elif type == "liveupdate_contributor_invite":
            LiveUpdateContributorInvitesByEvent.update_invite_permissions(
                c.liveupdate_event, user, permissions)

        row = form.closest("tr")
        editor = row.find(".permissions").data("PermissionEditor")
        editor.onCommit(permissions.dumps())

    @validatedForm(
        VLiveUpdateContributorWithPermission("manage"),
        VModhash(),
        user=VByName("id", thing_cls=Account),
    )
    def POST_rm_contributor(self, form, jquery, user):
        c.liveupdate_event.remove_contributor(user)

    @validatedForm(
        VLiveUpdateContributorWithPermission("update"),
        VModhash(),
        text=VMarkdown("body", max_length=4096),
    )
    def POST_update(self, form, jquery, text):
        if form.has_errors("body", errors.NO_TEXT,
                                   errors.TOO_LONG):
            return

        # create and store the new update
        update = LiveUpdate(data={
            "author_id": c.user._id,
            "body": text,
        })
        LiveUpdateStream.add_update(c.liveupdate_event, update)

        # tell the world about our new update
        builder = LiveUpdateBuilder(None)
        wrapped = builder.wrap_items([update])[0]
        rendered = wrapped.render(style="api")
        _broadcast(type="update", payload=rendered)

        # Queue up parsing any embeds
        queue_parse_embeds(c.liveupdate_event, update)

        # reset the submission form
        t = form.find("textarea")
        t.attr('rows', 3).html("").val("")

    @validatedForm(
        VModhash(),
        update=VLiveUpdate("id"),
    )
    def POST_delete_update(self, form, jquery, update):
        if form.has_errors("id", errors.NO_THING_ID):
            return

        if not (c.liveupdate_permissions.allow("edit") or
                (c.user_is_loggedin and update.author_id == c.user._id)):
            abort(403)

        update.deleted = True
        LiveUpdateStream.add_update(c.liveupdate_event, update)

        _broadcast(type="delete", payload=update._fullname)

    @validatedForm(
        VModhash(),
        update=VLiveUpdate("id"),
    )
    def POST_strike_update(self, form, jquery, update):
        if form.has_errors("id", errors.NO_THING_ID):
            return

        if not (c.liveupdate_permissions.allow("edit") or
                (c.user_is_loggedin and update.author_id == c.user._id)):
            abort(403)

        update.stricken = True
        LiveUpdateStream.add_update(c.liveupdate_event, update)

        _broadcast(type="strike", payload=update._fullname)

    @validatedForm(
        VLiveUpdateContributorWithPermission("close"),
        VModhash(),
    )
    def POST_close_stream(self, form, jquery):
        c.liveupdate_event.state = "complete"
        c.liveupdate_event._commit()

        queries.complete_event(c.liveupdate_event)

        _broadcast(type="complete", payload={})

        form.refresh()

    @validatedForm(
        VUser(),
        VModhash(),
        report_type=VOneOf("type", pages.REPORT_TYPES),
    )
    def POST_report(self, form, jquery, report_type):
        if form.has_errors("type", errors.INVALID_OPTION):
            return

        if c.user._spam or c.user.ignorereports:
            return

        already_reported = LiveUpdateReportsByAccount.get_report(
            c.user, c.liveupdate_event)
        if already_reported:
            self.abort403()

        LiveUpdateReportsByAccount.create(
            c.user, c.liveupdate_event, type=report_type)
        queries.report_event(c.liveupdate_event)

        try:
            default_subreddit = Subreddit._by_name(g.default_sr)
        except NotFound:
            pass
        else:
            not_yet_reported = g.cache.add(
                "lu_reported_" + str(c.liveupdate_event._id), 1, time=3600)
            if not_yet_reported:
                send_system_message(
                    default_subreddit,
                    subject="live update stream reported",
                    body=REPORTED_MESSAGE % {
                        "title": c.liveupdate_event.title,
                        "url": "/live/" + c.liveupdate_event._id,
                        "reason": pages.REPORT_TYPES[report_type],
                    },
                )

    @validatedForm(
        VAdmin(),
        VModhash(),
    )
    def POST_approve(self, form, jquery):
        c.liveupdate_event.banned = False
        c.liveupdate_event._commit()

        queries.unreport_event(c.liveupdate_event)

    @validatedForm(
        VAdmin(),
        VModhash(),
    )
    def POST_ban(self, form, jquery):
        c.liveupdate_event.banned = True
        c.liveupdate_event.banned_by = c.user.name
        c.liveupdate_event._commit()

        queries.unreport_event(c.liveupdate_event)


class LiveUpdateEventBuilder(IDBuilder):
    def thing_lookup(self, names):
        return LiveUpdateEvent._byID(names, return_dict=False)

    def wrap_items(self, items):
        return [self.wrap(item) for item in items]

    def keep_item(self, item):
        return True


class LiveUpdateReportedEventBuilder(LiveUpdateEventBuilder):
    def wrap_items(self, items):
        wrapped = LiveUpdateEventBuilder.wrap_items(self, items)
        reports_by_event = LiveUpdateReportsByEvent._byID(
            [w._id for w in wrapped])

        for w in wrapped:
            report_types = []
            if w._id in reports_by_event:
                report_types = reports_by_event[w._id]._values().values()
            w.reports_by_type = collections.Counter(report_types)
        return wrapped


@add_controller
class LiveUpdateEventsController(RedditController):
    def GET_home(self):
        return pages.LiveUpdateMetaPage(
            title=_("reddit live"),
            content=pages.LiveUpdateHome(),
            page_classes=["liveupdate-home"],
        ).render()

    @validate(
        VEmployee(),
        num=VLimit("limit", default=25, max_limit=100),
        after=VLiveUpdateEvent("after"),
        before=VLiveUpdateEvent("before"),
        count=VCount("count"),
    )
    def GET_listing(self, filter, num, after, before, count):
        reverse = False
        if before:
            after = before
            reverse = True

        builder_cls = LiveUpdateEventBuilder
        wrapper = Wrapped
        listing_cls = Listing

        if filter == "open":
            title = _("live threads")
            query = queries.get_live_events("new", "all")
        elif filter == "closed":
            title = _("closed threads")
            query = queries.get_complete_events("new", "all")
        elif filter == "reported":
            if not c.user_is_admin:
                self.abort403()

            title = _("reported threads")
            query = queries.get_reported_events()
            builder_cls = LiveUpdateReportedEventBuilder
            wrapper = pages.LiveUpdateReportedEventRow
            listing_cls = pages.LiveUpdateReportedEventListing
        else:
            self.abort404()

        builder = builder_cls(
            query,
            num=num,
            after=after,
            reverse=reverse,
            count=count,
            wrap=wrapper,
        )

        listing = listing_cls(builder)

        return pages.LiveUpdateMetaPage(
            title=title,
            content=listing.listing(),
        ).render()

    @validate(
        VUser(),
    )
    def GET_create(self):
        return pages.LiveUpdateMetaPage(
            title=_("create live update stream"),
            content=pages.LiveUpdateCreate(),
        ).render()

    @validatedForm(
        VUser(),
        VModhash(),
        VRatelimit(rate_user=True, prefix="liveupdate_create_"),
        **EVENT_CONFIGURATION_VALIDATORS
    )
    def POST_create(self, form, jquery, title, description):
        if not is_event_configuration_valid(form):
            return

        if form.has_errors("ratelimit", errors.RATELIMIT):
            return
        VRatelimit.ratelimit(
            rate_user=True, prefix="liveupdate_create_", seconds=60)

        event = LiveUpdateEvent.new(id=None, title=title)
        event.add_contributor(c.user, ContributorPermissionSet.SUPERUSER)
        queries.create_event(event)

        form.redirect("/live/" + event._id)


@add_controller
class LiveUpdateEmbedController(MinimalController):
    def __before__(self, event):
        MinimalController.__before__(self)

        if event:
            try:
                c.liveupdate_event = LiveUpdateEvent._byID(event)
            except tdb_cassandra.NotFound:
                pass

        if not c.liveupdate_event:
            self.abort404()

    @validate(
        liveupdate=VLiveUpdate('liveupdate'),
        embed_index=VInt('embed_index', min=0)
    )
    def GET_mediaembed(self, liveupdate, embed_index):
        if c.errors or request.host != g.media_domain:
            # don't serve up untrusted content except on our
            # specifically untrusted domain
            abort(404)

        try:
            media_object = liveupdate.media_objects[embed_index]
        except IndexError:
            abort(404)

        embed = get_live_media_embed(media_object)

        if not embed:
            abort(404)

        content = embed.content
        c.allow_framing = True

        args = {
            "body": content,
            "unknown_dimensions": not (embed.width and embed.height),
            "js_context": {
                "liveupdate_id": unicode(liveupdate._id),  # UUID serializing
                "embed_index": embed_index,
            }
        }

        return pages.LiveUpdateMediaEmbedBody(**args).render()
