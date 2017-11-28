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
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import mapper, attributes, object_mapper
from sqlalchemy.orm.properties import RelationshipProperty, ColumnProperty
from sqlalchemy import Table, Column, ForeignKeyConstraint, Integer
from sqlalchemy import util


def col_references_table(col, table):
    for fk in col.foreign_keys:
        if fk.references(table):
            return True
    return False


def _is_versioning_col(col):
    return "version_meta" in col.info


def _history_mapper(local_mapper):  # noqa (C901 too complex)
    cls = local_mapper.class_

    # set the "active_history" flag
    # on on column-mapped attributes so that the old version
    # of the info is always loaded (currently sets it on all attributes)
    for prop in local_mapper.iterate_properties:
        getattr(local_mapper.class_, prop.key).impl.active_history = True

    super_mapper = local_mapper.inherits
    super_history_mapper = getattr(cls, '__history_mapper__', None)

    polymorphic_on = None
    super_fks = []

    def _col_copy(col):
        orig = col
        col = col.copy()
        orig.info['history_copy'] = col
        col.unique = False

        # if the column is nullable, we could end up overwriting an on-purpose null value with a default.
        # if it's not nullable, however, the default may be relied upon to correctly set values within the database,
        # so we should preserve it
        if col.nullable:
            col.default = col.server_default = None
        return col

    properties = util.OrderedDict()
    if not super_mapper or \
            local_mapper.local_table is not super_mapper.local_table:
        cols = []
        version_meta = {"version_meta": True}
        for column in local_mapper.local_table.c:
            if _is_versioning_col(column):
                continue

            col = _col_copy(column)

            if super_mapper and \
                    col_references_table(column, super_mapper.local_table):
                super_fks.append(
                    (
                        col.key,
                        list(super_history_mapper.local_table.primary_key)[0]
                    )
                )

            cols.append(col)

            if column is local_mapper.polymorphic_on:
                polymorphic_on = col

            orig_prop = local_mapper.get_property_by_column(column)
            # carry over column re-mappings
            if len(orig_prop.columns) > 1 or \
                    orig_prop.columns[0].key != orig_prop.key:
                properties[orig_prop.key] = tuple(
                    col.info['history_copy'] for col in orig_prop.columns)

        if super_mapper:
            super_fks.append(
                (
                    'version', super_history_mapper.local_table.c.version
                )
            )

        # "version" stores the integer version id.  This column is
        # required.
        cols.append(
            Column(
                'version', Integer, primary_key=True,
                autoincrement=False, info=version_meta))

        if super_fks:
            cols.append(ForeignKeyConstraint(*zip(*super_fks)))

        table = Table(
            local_mapper.local_table.name + '_history',
            local_mapper.local_table.metadata,
            *cols,
            schema=local_mapper.local_table.schema
        )
    else:
        # single table inheritance.  take any additional columns that may have
        # been added and add them to the history table.
        for column in local_mapper.local_table.c:
            if column.key not in super_history_mapper.local_table.c:
                col = _col_copy(column)
                super_history_mapper.local_table.append_column(col)
        table = None

    if super_history_mapper:
        bases = (super_history_mapper.class_,)

        if table is not None:
            properties['changed'] = (
                (table.c.changed, ) +
                tuple(super_history_mapper.attrs.changed.columns)
            )

    else:
        bases = local_mapper.base_mapper.class_.__bases__
    versioned_cls = type.__new__(type, "%sHistory" % cls.__name__, bases, {})

    m = mapper(
        versioned_cls,
        table,
        inherits=super_history_mapper,
        polymorphic_on=polymorphic_on,
        polymorphic_identity=local_mapper.polymorphic_identity,
        properties=properties
    )
    cls.__history_mapper__ = m

    if not super_history_mapper:
        local_mapper.local_table.append_column(
            Column('version', Integer, default=1, nullable=False)
        )
        local_mapper.add_property(
            "version", local_mapper.local_table.c.version)


class Versioned(object):
    @declared_attr
    def __mapper_cls__(cls):
        def map(cls, *arg, **kw):
            mp = mapper(cls, *arg, **kw)
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

    history = history_cls()
    obj_mapper = object_mapper(obj)

    obj_state = attributes.instance_state(obj)
    data = {}
    for prop in obj_mapper.iterate_properties:

        # expired object attributes and also deferred cols might not
        # be in the dict.  force it them load no matter what by using getattr().
        if prop.key not in obj_state.dict:
            getattr(obj, prop.key)

        # if prop is a normal col just set it on history model
        if isinstance(prop, ColumnProperty):
            if not data.get(prop.key):
                data[prop.key] = getattr(obj, prop.key)

        # if the prop is a relationship property and there is a
        # corresponding prop on hist object then set the
        # relevant "_id" prop to the id of the current object.prop.id.
        # This is so foreign keys get set on history when
        # the source object is new and therefore property foo_id does
        # not yet have a value before insert

        elif isinstance(prop, RelationshipProperty):
            if hasattr(history, prop.key + '_id'):
                foreign_obj = getattr(obj, prop.key)
                # if it's a nullable relationship, foreign_obj will be None, and we actually want to record that
                data[prop.key + '_id'] = getattr(foreign_obj, 'id', None)

    if not obj.version:
        obj.version = 1
        obj.created_at = datetime.datetime.utcnow()
    else:
        obj.version += 1
        now = datetime.datetime.utcnow()
        obj.updated_at = now
        data['updated_at'] = now

    data['version'] = obj.version
    data['created_at'] = obj.created_at

    for key, value in data.items():
        if not hasattr(history_cls, key):
            raise AttributeError("{} has no attribute '{}'".format(history_cls.__name__, key))
        setattr(history, key, value)

    return history
