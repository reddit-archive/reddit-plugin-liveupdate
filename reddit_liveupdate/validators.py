import uuid

import pytz

from pylons import c
from pylons.controllers.util import abort

from r2.lib.validator import Validator, VPermissions
from r2.lib.db import tdb_cassandra
from r2.lib.errors import errors

from reddit_liveupdate import models
from reddit_liveupdate.permissions import ReporterPermissionSet


class VLiveUpdateID(Validator):
    def run(self, fullname):
        if not fullname or not fullname.startswith("LiveUpdate_"):
            return

        id = fullname[len("LiveUpdate_"):]

        try:
            return uuid.UUID(id)
        except (ValueError, TypeError):
            return


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


class VLiveUpdateReporterWithPermission(Validator):
    def __init__(self, permission):
        self.permission = permission
        Validator.__init__(self)

    def run(self):
        if not c.liveupdate_permissions.allow(self.permission):
            abort(403, "Forbidden")


class VTimeZone(Validator):
    def run(self, timezone_name):
        try:
            return pytz.timezone(timezone_name)
        except pytz.exceptions.UnknownTimeZoneError:
            self.set_error(errors.INVALID_TIMEZONE)


class VLiveUpdatePermissions(VPermissions):
    types = {
        "liveupdate_reporter": ReporterPermissionSet,
    }
