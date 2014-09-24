import uuid

from pylons import c
from pylons.controllers.util import abort

from r2.lib.validator import (
    Validator,
    VBoolean,
    VLength,
    VMarkdown,
    VPermissions,
)
from r2.lib.db import tdb_cassandra
from r2.lib.errors import errors

from reddit_liveupdate import models
from reddit_liveupdate.permissions import ContributorPermissionSet


class VLiveUpdateEvent(Validator):
    def run(self, id):
        if not id:
            return None

        try:
            return models.LiveUpdateEvent._byID(id)
        except tdb_cassandra.NotFound:
            return None


class VLiveUpdateID(Validator):
    def run(self, fullname):
        if not fullname or not fullname.startswith("LiveUpdate_"):
            return

        id = fullname[len("LiveUpdate_"):]

        try:
            return uuid.UUID(id)
        except (ValueError, TypeError):
            return

    def param_docs(self):
        return {
            self.param: "the ID of a single update. e.g. `LiveUpdate_ff87068e-a126-11e3-9f93-12313b0b3603`",
        }


class VLiveUpdate(VLiveUpdateID):
    def run(self, fullname):
        id = VLiveUpdateID.run(self, fullname)

        if id:
            try:
                return models.LiveUpdateStream.get_update(
                    c.liveupdate_event, id)
            except tdb_cassandra.NotFound:
                pass

        self.set_error(errors.NO_THING_ID)


class VLiveUpdateContributorWithPermission(Validator):
    def __init__(self, permission):
        self.permission = permission
        Validator.__init__(self)

    def run(self):
        if not c.liveupdate_permissions.allow(self.permission):
            abort(403, "Forbidden")


class VLiveUpdatePermissions(VPermissions):
    types = {
        "liveupdate_contributor": ContributorPermissionSet,
        "liveupdate_contributor_invite": ContributorPermissionSet,
    }

    def param_docs(self):
        return {
            self.param[0]:
                "one of (%s)" % ", ".join("`%s`" % s for s in self.types),
            self.param[1]:
                "permission description e.g. `+update,+edit,-manage`",
        }


EVENT_CONFIGURATION_VALIDATORS = {
    "title": VLength("title", max_length=120),
    "description": VMarkdown("description", max_length=120, empty_error=None),
    "resources": VMarkdown("resources", empty_error=None),
    "nsfw": VBoolean("nsfw"),
}


def is_event_configuration_valid(form):
    if form.has_errors("title", errors.NO_TEXT,
                                errors.TOO_LONG):
        return False

    if form.has_errors("description", errors.TOO_LONG):
        return False

    if form.has_errors("resources", errors.TOO_LONG):
        return False

    return True
