import datetime
import json
import uuid

import pytz

from pycassa.util import convert_uuid_to_time
from pycassa.system_manager import TIME_UUID_TYPE, UTF8_TYPE

from r2.lib import utils
from r2.lib.db import tdb_cassandra
from r2.models import query_cache

from reddit_liveupdate.contrib import simpleflake
from reddit_liveupdate.permissions import ContributorPermissionSet


class LiveUpdateEvent(tdb_cassandra.Thing):
    _contributor_prefix = "contributor_"

    _use_db = True
    _read_consistency_level = tdb_cassandra.CL.ONE
    _write_consistency_level = tdb_cassandra.CL.QUORUM

    _int_props = (
        "active_visitors",
    )
    _bool_props = (
        "active_visitors_fuzzed",
        "banned",
    )
    _defaults = {
        "description": "",
        "resources": "",
        # one of "live", "complete"
        "state": "live",
        "active_visitors": 0,
        "active_visitors_fuzzed": True,
        "banned": False,
        "banned_by": "(unknown)",
    }

    @classmethod
    def _contributor_key(cls, user):
        return "%s%s" % (cls._contributor_prefix, user._id36)

    def add_contributor(self, user, permissions):
        self[self._contributor_key(user)] = permissions.dumps()
        self._commit()

    def update_contributor_permissions(self, user, permissions):
        return self.add_contributor(user, permissions)

    def remove_contributor(self, user):
        del self[self._contributor_key(user)]
        self._commit()

    def get_permissions(self, user):
        permission_string = self._t.get(self._contributor_key(user), "")
        return ContributorPermissionSet.loads(permission_string)

    @property
    def _fullname(self):
        return self._id

    @property
    def _id36(self):
        # this is a bit of a hack but lets us use events in denormalizedrels
        return self._id

    @property
    def contributors(self):
        return {int(k[len(self._contributor_prefix):], 36):
                    ContributorPermissionSet.loads(v)
                for k, v in self._t.iteritems()
                if k.startswith(self._contributor_prefix)}

    @classmethod
    def new(cls, id, title, **properties):
        if not id:
            id = utils.to36(simpleflake.simpleflake())
        event = cls(id, title=title, **properties)
        event._commit()
        return event

    @classmethod
    def update_activity(cls, id, activity, fuzzed):
        thing = cls(_id=id, _partial=["active_visitors"])
        thing._committed = True  # hack to prevent overwriting the date attr
        thing.active_visitors = activity
        thing.active_visitors_fuzzed = fuzzed
        thing._commit()
        return thing


class FocusQuery(object):
    """A query-like object for focused updates."""
    def __init__(self, items):
        self.items = items
        self._rules = []

    def _reverse(self):
        self.items.reverse()

    def _after(self, id):
        pass

    def __iter__(self):
        return iter(self.items)


class LiveUpdateStream(tdb_cassandra.View):
    _use_db = True
    _connection_pool = "main"
    _compare_with = TIME_UUID_TYPE
    _read_consistency_level = tdb_cassandra.CL.ONE
    _write_consistency_level = tdb_cassandra.CL.QUORUM
    _extra_schema_creation_args = {
        "default_validation_class": UTF8_TYPE,
    }

    @classmethod
    def add_update(cls, event, update):
        columns = cls._obj_to_column(update)
        cls._set_values(event._id, columns)

    @classmethod
    def get_update(cls, event, id):
        thing = cls._byID(event._id, properties=[id])

        try:
            data = thing._t[id]
        except KeyError:
            raise tdb_cassandra.NotFound, "<LiveUpdate %s>" % id
        else:
            return LiveUpdate.from_json(id, data)

    @classmethod
    def _obj_to_column(cls, entries):
        entries, is_single = utils.tup(entries, ret_is_single=True)
        columns = [{entry._id: entry.to_json()} for entry in entries]
        return columns[0] if is_single else columns

    @classmethod
    def _column_to_obj(cls, columns):
        # columns = [{colname: colvalue}]
        return [LiveUpdate.from_json(*column.popitem())
                for column in utils.tup(columns)]

    @classmethod
    def query_focus(cls, event, id):
        return FocusQuery([cls.get_update(event, id)])


class LiveUpdate(object):
    __slots__ = ("_id", "_data")
    defaults = {
        "deleted": False,
        "stricken": False,
        "_spam": False,
        "media_objects": [],
    }

    def __init__(self, id=None, data=None):
        if not id:
            id = uuid.uuid1()
        self._id = id
        self._data = data or {}

    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError:
            try:
                return LiveUpdate.defaults[name]
            except KeyError:
                raise AttributeError, name

    def __setattr__(self, name, value):
        if name in self.__slots__:
            object.__setattr__(self, name, value)
        else:
            self._data[name] = value

    def to_json(self):
        return json.dumps(self._data)

    @classmethod
    def from_json(cls, id, value):
        return cls(id, json.loads(value))

    @property
    def _date(self):
        timestamp = convert_uuid_to_time(self._id)
        return datetime.datetime.fromtimestamp(timestamp, pytz.UTC)

    @property
    def _fullname(self):
        return "%s_%s" % (self.__class__.__name__, self._id)

    @property
    def embeds(self):
        """Return the media objects in a whitelisted, json-ready format."""

        embeds = []
        for media_object in self.media_objects:
            try:
                embeds.append({
                    "url": media_object['oembed']['url'],
                    "width": media_object['oembed']['width'],
                    "height": media_object['oembed']['height'],
                })
            except KeyError:
                pass
        return embeds


class ActiveVisitorsByLiveUpdateEvent(tdb_cassandra.View):
    _use_db = True
    _connection_pool = 'main'
    _ttl = datetime.timedelta(minutes=15)

    _extra_schema_creation_args = dict(
        key_validation_class=tdb_cassandra.ASCII_TYPE,
    )

    _read_consistency_level  = tdb_cassandra.CL.ONE
    _write_consistency_level = tdb_cassandra.CL.ANY

    @classmethod
    def touch(cls, event_id, hash):
        cls._set_values(event_id, {hash: ''})

    @classmethod
    def get_count(cls, event_id):
        return cls._cf.get_count(event_id)


class LiveUpdateActivityHistoryByEvent(tdb_cassandra.View):
    _use_db = True
    _connection_pool = "main"
    _compare_with = "TimeUUIDType"
    _value_type = "bytes"  # use pycassa, not tdb_c*, to serialize
    _read_consistency_level = tdb_cassandra.CL.QUORUM
    _write_consistency_level = tdb_cassandra.CL.QUORUM
    _extra_schema_creation_args = {
        "default_validation_class": "IntegerType",
    }

    @classmethod
    def record_activity(cls, event_id, activity_count):
        cls._set_values(event_id, {uuid.uuid1(): activity_count})


class InviteNotFoundError(Exception):
    pass


class LiveUpdateContributorInvitesByEvent(tdb_cassandra.View):
    _use_db = True
    _compare_with = "AsciiType"
    _value_type = "str"
    _read_consistency_level = tdb_cassandra.CL.QUORUM
    _write_consistency_level = tdb_cassandra.CL.QUORUM
    _extra_schema_creation_args = {
        "key_validation_class": "AsciiType",
    }

    @classmethod
    def create(cls, event, user, permissions):
        cls._set_values(event._id, {user._id36: permissions.dumps()})

    @classmethod
    def update_invite_permissions(cls, event, user, permissions):
        cls.create(event, user, permissions)

    @classmethod
    def get(cls, event, user):
        try:
            row = cls._byID(event._id, properties=[user._id36])
            value = row[user._id36]
        except (tdb_cassandra.NotFound, KeyError):
            raise InviteNotFoundError
        return ContributorPermissionSet.loads(value)

    @classmethod
    def get_all(cls, event):
        try:
            invites = cls._byID(event._id)._values()
        except tdb_cassandra.NotFound:
            return {}
        else:
            return {int(k, 36): ContributorPermissionSet.loads(v)
                    for k, v in invites.iteritems()}

    @classmethod
    def remove(cls, event, user):
        cls._remove(event._id, [user._id36])


class LiveUpdateReportsByAccount(tdb_cassandra.DenormalizedRelation):
    _use_db = True
    _last_modified_name = "LiveUpdateReport"
    _views = []
    _ttl = datetime.timedelta(hours=12)

    @classmethod
    def value_for(cls, thing1, thing2, type):
        return type

    @classmethod
    def get_report(cls, account, event):
        reports = cls.fast_query(account, [event])
        return reports.get((account, event))


@tdb_cassandra.view_of(LiveUpdateReportsByAccount)
class LiveUpdateReportsByEvent(tdb_cassandra.View):
    _use_db = True
    _compare_with = "AsciiType"
    _ttl = datetime.timedelta(hours=48)
    _extra_schema_creation_args = {
        "key_validation_class": "AsciiType",
        "default_validation_class": "AsciiType",
    }

    @classmethod
    def create(cls, thing1, thing2s, type):
        assert len(thing2s) == 1
        thing2 = thing2s[0]
        cls._set_values(thing2._id, {thing1._id36: type})

    @classmethod
    def destroy(cls, thing1, thing2s, type):
        raise NotImplementedError


class LiveUpdateQueryCache(query_cache._BaseQueryCache):
    _use_db = True
