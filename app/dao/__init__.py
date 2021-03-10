from sqlalchemy.exc import SQLAlchemyError

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

    def update_instance(self, inst, update_dict, _commit=True):
        # Make sure the id is not included in the update_dict
        update_dict.pop('id')
        self.Meta.model.query.filter_by(id=inst.id).update(update_dict)
        if _commit:
            db.session.commit()

    def delete_instance(self, inst, _commit=True):
        db.session.delete(inst)
        if _commit:
            db.session.commit()
