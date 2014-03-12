import hashlib
import os

from pylons import g, c, request, response
from pylons.i18n import _

from r2.controllers import add_controller
from r2.controllers.reddit_base import RedditController, base_listing
from r2.lib import websockets
from r2.lib.base import BaseController, abort
from r2.lib.db import tdb_cassandra
from r2.lib.filters import safemarkdown
from r2.lib.validator import (
    validate,
    validatedForm,
    VBoolean,
    VByName,
    VCount,
    VExistingUname,
    VLength,
    VLimit,
    VMarkdown,
    VModhash,
)
from r2.models import QueryBuilder, Account, LinkListing, SimpleBuilder
from r2.lib.errors import errors
from r2.lib.utils import url_links_builder

from reddit_liveupdate import pages
from reddit_liveupdate.models import (
    LiveUpdate,
    LiveUpdateEvent,
    LiveUpdateStream,
    ActiveVisitorsByLiveUpdateEvent,
)
from reddit_liveupdate.permissions import ReporterPermissionSet
from reddit_liveupdate.validators import (
    VLiveUpdate,
    VLiveUpdateReporterWithPermission,
    VLiveUpdatePermissions,
    VLiveUpdateID,
    VTimeZone,
)


def send_websocket_broadcast(type, payload):
    websockets.send_broadcast(namespace="/live/" + c.liveupdate_event._id,
                              type=type, payload=payload)


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


class LiveUpdateReporter(object):
    def __init__(self, account, permissions):
        self.account = account
        self.permissions = permissions

    @property
    def _id(self):
        return self.account._id


class LiveUpdateReporterBuilder(SimpleBuilder):
    def __init__(self, event, editable):
        self.event = event
        self.editable = editable

        perms_by_reporter = event.reporters
        reporter_accounts = Account._byID(perms_by_reporter.keys(), data=True)
        reporters = [LiveUpdateReporter(account, perms_by_reporter[account._id])
                     for account in reporter_accounts.itervalues()]
        reporters.sort(key=lambda r: r.account.name)

        SimpleBuilder.__init__(
            self,
            reporters,
            keep_fn=self.keep_item,
            wrap=self.wrap_item,
            skip=False,
            num=0,
        )

    def keep_item(self, item):
        return not item.account._deleted

    def wrap_item(self, item):
        return pages.ReporterTableItem(
            item,
            self.event,
            editable=self.editable,
        )

    def wrap_items(self, items):
        wrapped = []
        for item in items:
            wrapped.append(self.wrap_item(item))
        return wrapped


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

        if c.user_is_loggedin:
            c.liveupdate_permissions = \
                    c.liveupdate_event.get_permissions(c.user)
            if c.user_is_admin:
                c.liveupdate_permissions = ReporterPermissionSet.SUPERUSER
        else:
            c.liveupdate_permissions = ReporterPermissionSet.NONE

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
        content = pages.LiveUpdateEvent(
            event=c.liveupdate_event,
            listing=listing.listing(),
            show_sidebar=not is_embed,
        )

        # don't generate a url unless this is the main page of an event
        websocket_url = None
        if c.liveupdate_event.state == "live" and not after and not before:
            websocket_url = websockets.make_url(
                "/live/" + c.liveupdate_event._id, max_age=24 * 60 * 60)

        if not is_embed:
            return pages.LiveUpdatePage(
                content=content,
                websocket_url=websocket_url,
            ).render()
        else:
            # embeds are always logged out and therefore safe for frames.
            c.liveupdate_permissions = ReporterPermissionSet.NONE
            c.allow_framing = True

            return pages.LiveUpdateEmbed(
                content=content,
                websocket_url=websocket_url,
            ).render()


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
        return pages.LiveUpdatePage(
            content=listing,
        ).render()

    @validate(
        VLiveUpdateReporterWithPermission("settings"),
    )
    def GET_edit(self):
        return pages.LiveUpdatePage(
            content=pages.LiveUpdateEventConfiguration(),
        ).render()

    @validatedForm(
        VLiveUpdateReporterWithPermission("settings"),
        VModhash(),
        title=VLength("title", max_length=120),
        description=VMarkdown("description", empty_error=None),
        timezone=VTimeZone("timezone"),
    )
    def POST_edit(self, form, jquery, title, description, timezone):
        if form.has_errors("title", errors.NO_TEXT,
                                    errors.TOO_LONG):
            return

        if form.has_errors("description", errors.TOO_LONG):
            return

        if form.has_errors("timezone", errors.INVALID_TIMEZONE):
            return

        changes = {}
        if title != c.liveupdate_event.title:
            changes["title"] = title
        if description != c.liveupdate_event.description:
            changes["description"] = safemarkdown(description, wrap=False)
        send_websocket_broadcast(type="settings", payload=changes)

        c.liveupdate_event.title = title
        c.liveupdate_event.description = description
        c.liveupdate_event.timezone = timezone.zone
        c.liveupdate_event._commit()

        form.set_html(".status", _("saved"))
        form.refresh()

    # TODO: pass listing params on
    def GET_reporters(self):
        editable = c.liveupdate_permissions.allow("manage")
        builder = LiveUpdateReporterBuilder(c.liveupdate_event, editable)
        listing = pages.ReporterListing(
            c.liveupdate_event,
            builder,
            editable=editable,
        ).listing()

        return pages.LiveUpdatePage(
            content=listing,
        ).render()

    @validatedForm(
        VLiveUpdateReporterWithPermission("manage"),
        VModhash(),
        user=VExistingUname("name"),
        type_and_perms=VLiveUpdatePermissions("type", "permissions"),
    )
    def POST_add_reporter(self, form, jquery, user, type_and_perms):
        if form.has_errors("name", errors.USER_DOESNT_EXIST,
                                   errors.NO_USER):
            return
        if form.has_errors("type", errors.INVALID_PERMISSION_TYPE):
            return
        if form.has_errors("permissions", errors.INVALID_PERMISSIONS):
            return

        type, permissions = type_and_perms
        c.liveupdate_event.add_reporter(user, permissions)

        # TODO: send PM to new reporter

        # add the user to the table
        reporter = LiveUpdateReporter(user, permissions)
        user_row = pages.ReporterTableItem(reporter, c.liveupdate_event,
                                           editable=True)
        jquery(".liveupdate_reporter-table").show(
            ).find("table").insert_table_rows(user_row)

    @validatedForm(
        VLiveUpdateReporterWithPermission("manage"),
        VModhash(),
        user=VExistingUname("name"),
        type_and_perms=VLiveUpdatePermissions("type", "permissions"),
    )
    def POST_set_reporter_permissions(self, form, jquery, user, type_and_perms):
        if form.has_errors("name", errors.USER_DOESNT_EXIST,
                                   errors.NO_USER):
            return
        if form.has_errors("type", errors.INVALID_PERMISSION_TYPE):
            return
        if form.has_errors("permissions", errors.INVALID_PERMISSIONS):
            return

        type, permissions = type_and_perms
        c.liveupdate_event.update_reporter_permissions(user, permissions)

        row = form.closest("tr")
        editor = row.find(".permissions").data("PermissionEditor")
        editor.onCommit(permissions.dumps())

    @validatedForm(
        VLiveUpdateReporterWithPermission("manage"),
        VModhash(),
        user=VByName("id", thing_cls=Account),
    )
    def POST_rm_reporter(self, form, jquery, user):
        c.liveupdate_event.remove_reporter(user)

    @validatedForm(
        VLiveUpdateReporterWithPermission("update"),
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
        wrapped = builder.wrap_items([update])
        rendered = [w.render() for w in wrapped]
        send_websocket_broadcast(type="update", payload=rendered)

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

        send_websocket_broadcast(type="delete", payload=update._fullname)

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

        send_websocket_broadcast(type="strike", payload=update._fullname)
