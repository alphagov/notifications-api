"""Versioned mixin class and other utilities.

This is an adapted version of:

https://bitbucket.org/zzzeek/sqlalchemy/raw/master/examples/versioned_history/history_meta.py

It does not use the create_version function from the orginal which looks for changes to models
as we just insert a copy of a model to the history table on create or update.

Also it does not add a created_at timestamp to the history table as we already have created_at
and updated_at timestamps.

Lastly when to create a version is done manually in dao_utils version decorator and not via
session events.

"""

import datetime
import uuid

from sqlalchemy import Column, Integer, Table, util
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import Mapper, attributes, object_mapper
from sqlalchemy.orm.properties import ColumnProperty, RelationshipProperty


def col_references_table(col, table):
    for fk in col.foreign_keys:
        if fk.references(table):
            return True
    return False


def _is_versioning_col(col):
    return "version_meta" in col.info


def _history_mapper(local_mapper):
    cls = local_mapper.class_

    # set the "active_history" flag
    # on on column-mapped attributes so that the old version
    # of the info is always loaded (currently sets it on all attributes)
    for prop in local_mapper.iterate_properties:
        prop.active_history = True

    def _col_copy(col):
        orig = col
        col = col.copy()
        orig.info["history_copy"] = col
        col.unique = False

        # if the column is nullable, we could end up overwriting an on-purpose null value with a default.
        # if it's not nullable, however, the default may be relied upon to correctly set values within the database,
        # so we should preserve it
        if col.nullable:
            col.default = col.server_default = None
        return col

    properties = util.OrderedDict()
    cols = []
    version_meta = {"version_meta": True}
    for column in local_mapper.local_table.c:
        col = _col_copy(column)

        cols.append(col)

    # "version" stores the integer version id.  This column is required.
    cols.append(Column("version", Integer, primary_key=True, autoincrement=False, info=version_meta))

    table = Table(
        f"{local_mapper.local_table.name}_history",
        local_mapper.local_table.metadata,
        *cols,
        schema=local_mapper.local_table.schema,
    )
    versioned_cls = type.__new__(type, f"{cls.__name__}History", cls.__bases__, {})

    m = local_mapper.registry.map_imperatively(
        versioned_cls,
        table,
        properties=properties,
    )
    cls.__history_mapper__ = m

    local_mapper.local_table.append_column(Column("version", Integer, default=1, nullable=False))
    local_mapper.add_property("version", local_mapper.local_table.c.version)


class Versioned:
    @declared_attr
    def __mapper_cls__(cls):
        def map(cls, *arg, **kw):
            mp = Mapper(cls, *arg, **kw)
            _history_mapper(mp)
            return mp

        return map

    @classmethod
    def get_history_model(cls):
        history_mapper = cls.__history_mapper__
        return history_mapper.class_


def create_history(obj, history_cls=None):
    if not history_cls:
        history_mapper = obj.__history_mapper__
        history_cls = history_mapper.class_

    obj_mapper = object_mapper(obj)

    obj_state = attributes.instance_state(obj)
    data = {}
    for prop in obj_mapper.iterate_properties:
        # expired object attributes and also deferred cols might not
        # be in the dict.  force it them load no matter what by using getattr().
        if prop.key not in obj_state.dict:
            getattr(obj, prop.key)

        # Ensure the object has an ID before creating the corresponding history object
        if prop.key == "id" and obj.id is None:
            obj.id = uuid.uuid4()

        # if prop is a normal col just set it on history model
        if isinstance(prop, ColumnProperty):
            # if the field is normally accessed via a property/hybrid property, then
            # prop.key might be for example `_bearer_token`. However, in the history model
            # we don't have these properties, and instead the column's python variable name
            # will match the database (eg `bearer_token`). We want to always write to a
            # field that matches the database column name.
            column_name = prop.columns[0].name

            if not data.get(column_name):
                data[column_name] = getattr(obj, prop.key)

        # if the prop is a relationship property and there is a
        # corresponding prop on hist object then set the
        # relevant "_id" prop to the id of the current object.prop.id.
        # This is so foreign keys get set on history when
        # the source object is new and therefore property foo_id does
        # not yet have a value before insert

        elif isinstance(prop, RelationshipProperty):
            if hasattr(history_cls, prop.key + "_id"):
                foreign_obj = getattr(obj, prop.key)
                # if it's a nullable relationship, foreign_obj will be None, and we actually want to record that
                data[prop.key + "_id"] = getattr(foreign_obj, "id", None)

    if not obj.version:
        obj.version = 1
        obj.created_at = datetime.datetime.utcnow()
    else:
        obj.version += 1
        now = datetime.datetime.utcnow()
        obj.updated_at = now
        data["updated_at"] = now

    data["version"] = obj.version
    data["created_at"] = obj.created_at

    return history_cls(**data)
