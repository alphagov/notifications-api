from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import MultiDict
from sqlalchemy.orm.relationships import RelationshipProperty
from app import db


# Should I use SQLAlchemyError?
class DAOException(SQLAlchemyError):
    pass


class DAOClass(object):

    class Meta:
        model = None

    def create_instance(self, inst, _commit=True):
        db.session.add(inst)
        if _commit:
            db.session.commit()

    def update_instance(self, inst, update_dict):
        # Make sure the id is not included in the update_dict
        update_dict.pop('id')
        self.Meta.model.query.filter_by(id=inst.id).update(update_dict)
        db.session.commit()

    def get_query(self, filter_by_dict={}):
        if isinstance(filter_by_dict, dict):
            filter_by_dict = MultiDict(filter_by_dict)
        query = self.Meta.model.query
        for k in filter_by_dict.keys():
            query = self._build_query(query, k, filter_by_dict.getlist(k))
        return query

    def delete_instance(self, inst):
        db.session.delete(inst)
        db.session.commit()

    def _build_query(self, query, key, values):
        # TODO Lots to do here to work with all types of filters.
        field = getattr(self.Meta.model, key, None)
        filters = getattr(self.Meta, 'filter', [key])
        if field and key in filters:
            if isinstance(field.property, RelationshipProperty):
                if len(values) == 1:
                    query = query.filter_by(**{key: field.property.mapper.class_.query.get(values[0])})
                elif len(values) > 1:
                    query = query.filter(field.in_(field.property.mapper.class_.query.any(values[0])))
            else:
                if len(values) == 1:
                    query = query.filter_by(**{key: values[0]})
                elif len(values) > 1:
                    query = query.filter(field.in_(values))
        return query
