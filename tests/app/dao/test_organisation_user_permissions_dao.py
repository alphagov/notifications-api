from app.constants import OrganisationUserPermissionTypes
from app.dao.organisation_user_permissions_dao import organisation_user_permissions_dao
from app.models import OrganisationUserPermissions


class TestOrganisationUserPermissionsDao:
    def test_can_add_and_get_and_remove_permissions(self, notify_db_session, sample_organisation, sample_user):
        sample_user.organisations = [sample_organisation]
        notify_db_session.commit()

        new_permissions = [
            OrganisationUserPermissions(user=sample_user, organisation=sample_organisation, permission=p)
            for p in [OrganisationUserPermissionTypes.can_make_services_live.value]
        ]
        organisation_user_permissions_dao.set_user_organisation_permission(
            sample_user,
            sample_organisation,
            new_permissions,
            _commit=True,
        )
        permissions = organisation_user_permissions_dao.get_permissions_by_user_id(
            user_id=sample_organisation.users[0].id
        )
        assert [i.permission for i in permissions] == [OrganisationUserPermissionTypes.can_make_services_live]

        organisation_user_permissions_dao.remove_user_organisation_permissions(sample_user, sample_organisation)
        permissions = organisation_user_permissions_dao.get_permissions_by_user_id(
            user_id=sample_organisation.users[0].id
        )
        assert len(permissions) == 0

    def test_get_permissions_by_user_id_returns_only_active_organisations(
        self, notify_db_session, sample_organisation, sample_user
    ):
        sample_organisation.active = False
        sample_user.organisations = [sample_organisation]
        notify_db_session.commit()

        new_permissions = [
            OrganisationUserPermissions(user=sample_user, organisation=sample_organisation, permission=p)
            for p in [OrganisationUserPermissionTypes.can_make_services_live.value]
        ]
        organisation_user_permissions_dao.set_user_organisation_permission(
            sample_user,
            sample_organisation,
            new_permissions,
            _commit=True,
        )
        permissions = organisation_user_permissions_dao.get_permissions_by_user_id(
            user_id=sample_organisation.users[0].id
        )
        assert len(permissions) == 0
