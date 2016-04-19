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


from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import mapper
from sqlalchemy import Table, Column, ForeignKeyConstraint, Integer
from sqlalchemy import util


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


def versioned_objects(iter):
    for obj in iter:
        if hasattr(obj, '__history_mapper__'):
            yield obj
