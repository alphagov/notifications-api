from app import db
from app.dao import DAOClass
from app.models import Organisation, OrganisationUserPermissions, User


class OrganisationUserPermissionsDao(DAOClass):
    class Meta:
        model = OrganisationUserPermissions

    def remove_user_organisation_permissions(self, user: User, organisation: Organisation):
        query = self.Meta.model.query.filter_by(user=user, organisation=organisation)
        query.delete()

    def remove_user_organisation_permissions_by_user(self, user: User):
        query = self.Meta.model.query.filter_by(user=user)
        query.delete()

    def set_user_organisation_permission(
        self,
        user: User,
        organisation: Organisation,
        permissions: list[OrganisationUserPermissions],
        _commit=False,
        replace=False,
    ):
        try:
            if replace:
                query = self.Meta.model.query.filter_by(user=user, organisation=organisation)
                query.delete()
            for p in permissions:
                p.user = user
                p.organisation = organisation
                self.create_instance(p, _commit=False)
        except Exception as e:
            if _commit:
                db.session.rollback()
            raise e
        else:
            if _commit:
                db.session.commit()

    def get_permissions_by_user_id(self, user_id):
        return (
            self.Meta.model.query.filter_by(user_id=user_id)
            .join(OrganisationUserPermissions.organisation)
            .filter(Organisation.active.is_(True))
            .order_by(OrganisationUserPermissions.permission)
            .all()
        )

    def get_permissions_by_user_id_and_organisation_id(self, user_id, organisation_id):
        return (
            self.Meta.model.query.filter_by(user_id=user_id)
            .join(OrganisationUserPermissions.organisation)
            .filter(Organisation.active.is_(True), Organisation.id == organisation_id)
            .order_by(OrganisationUserPermissions.permission)
            .all()
        )


organisation_user_permissions_dao = OrganisationUserPermissionsDao()
