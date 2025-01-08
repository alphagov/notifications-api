import uuid

import pytest

from app.dao.service_user_dao import dao_get_service_user
from app.models import TemplateFolder
from tests.app.db import (
    create_service,
    create_template,
    create_template_folder,
    create_user,
)
from tests.utils import QueryRecorder


def test_get_folders_for_service(admin_request, notify_db_session):
    s1 = create_service(service_name="a")
    s2 = create_service(service_name="b")

    tf1 = create_template_folder(s1)
    tf2 = create_template_folder(s1)

    create_template_folder(s2)

    resp = admin_request.get("template_folder.get_template_folders_for_service", service_id=s1.id)
    assert set(resp.keys()) == {"template_folders"}
    assert sorted(resp["template_folders"], key=lambda x: x["id"]) == sorted(
        [
            {
                "id": str(tf1.id),
                "name": "foo",
                "service_id": str(s1.id),
                "parent_id": None,
                "users_with_permission": [],
            },
            {
                "id": str(tf2.id),
                "name": "foo",
                "service_id": str(s1.id),
                "parent_id": None,
                "users_with_permission": [],
            },
        ],
        key=lambda x: x["id"],
    )


def test_get_folders_for_service_with_no_folders(sample_service, admin_request):
    resp = admin_request.get("template_folder.get_template_folders_for_service", service_id=sample_service.id)
    assert resp == {"template_folders": []}


def test_get_folders_returns_users_with_permission(admin_request, sample_service):
    user_1 = create_user(email="one@gov.uk")
    user_2 = create_user(email="two@gov.uk")
    user_3 = create_user(email="three@gov.uk")
    template_folder = create_template_folder(sample_service)

    sample_service.users = [user_1, user_2, user_3]

    service_user_1 = dao_get_service_user(user_1.id, sample_service.id)
    service_user_2 = dao_get_service_user(user_2.id, sample_service.id)

    service_user_1.folders = [template_folder]
    service_user_2.folders = [template_folder]

    resp = admin_request.get("template_folder.get_template_folders_for_service", service_id=sample_service.id)
    users_with_permission = resp["template_folders"][0]["users_with_permission"]

    assert len(users_with_permission) == 2
    assert str(user_1.id) in users_with_permission
    assert str(user_2.id) in users_with_permission


def test_get_folders_returns_users_with_permission_does_not_do_n_plus_1_sql_queries(
    admin_request, sample_service, notify_db_session
):
    users = [create_user(email=f"user-{_}@gov.uk") for _ in range(10)]
    template_folders = [create_template_folder(sample_service) for _ in range(25)]
    sample_service.users = users

    service_users = [dao_get_service_user(user.id, sample_service.id) for user in users]
    for service_user in service_users:
        service_user.folders = template_folders

    service_id = sample_service.id
    notify_db_session.commit()

    with QueryRecorder() as query_recorder:
        resp = admin_request.get("template_folder.get_template_folders_for_service", service_id=service_id)

    users_with_permission = resp["template_folders"][0]["users_with_permission"]

    assert len(users_with_permission) == 10
    assert all(str(user.id) in users_with_permission for user in users)
    assert len(query_recorder.queries) == 3


@pytest.mark.parametrize("has_parent", [True, False])
def test_create_template_folder(admin_request, sample_service, has_parent):
    existing_folder = create_template_folder(sample_service)

    parent_id = str(existing_folder.id) if has_parent else None

    resp = admin_request.post(
        "template_folder.create_template_folder",
        service_id=sample_service.id,
        _data={"name": "foo", "parent_id": parent_id},
        _expected_status=201,
    )

    assert resp["data"]["name"] == "foo"
    assert resp["data"]["service_id"] == str(sample_service.id)
    assert resp["data"]["parent_id"] == parent_id


@pytest.mark.parametrize("has_parent", [True, False])
def test_create_template_folder_sets_user_permissions(admin_request, sample_service, has_parent):
    user_1 = create_user(email="one@gov.uk")
    user_2 = create_user(email="two@gov.uk")
    user_3 = create_user(email="three@gov.uk", state="pending")
    existing_folder = create_template_folder(sample_service)
    sample_service.users = [user_1, user_2, user_3]
    service_user_1 = dao_get_service_user(user_1.id, sample_service.id)
    service_user_1.folders = [existing_folder]

    parent_id = str(existing_folder.id) if has_parent else None

    resp = admin_request.post(
        "template_folder.create_template_folder",
        service_id=sample_service.id,
        _data={"name": "foo", "parent_id": parent_id},
        _expected_status=201,
    )

    assert resp["data"]["name"] == "foo"
    assert resp["data"]["service_id"] == str(sample_service.id)
    assert resp["data"]["parent_id"] == parent_id

    if has_parent:
        assert resp["data"]["users_with_permission"] == [str(user_1.id)]
    else:
        assert sorted(resp["data"]["users_with_permission"]) == sorted([str(user_1.id), str(user_2.id)])


@pytest.mark.parametrize("missing_field", ["name", "parent_id"])
def test_create_template_folder_fails_if_missing_fields(admin_request, sample_service, missing_field):
    data = {"name": "foo", "parent_id": None}
    data.pop(missing_field)

    resp = admin_request.post(
        "template_folder.create_template_folder", service_id=sample_service.id, _data=data, _expected_status=400
    )

    assert resp == {
        "status_code": 400,
        "errors": [{"error": "ValidationError", "message": f"{missing_field} is a required property"}],
    }


def test_create_template_folder_fails_if_unknown_parent_id(admin_request, sample_service):
    resp = admin_request.post(
        "template_folder.create_template_folder",
        service_id=sample_service.id,
        _data={"name": "bar", "parent_id": str(uuid.uuid4())},
        _expected_status=400,
    )

    assert resp["result"] == "error"
    assert resp["message"] == "parent_id not found"


def test_create_template_folder_fails_if_parent_id_from_different_service(admin_request, sample_service):
    s1 = create_service(service_name="a")
    parent_folder_id = create_template_folder(s1).id

    resp = admin_request.post(
        "template_folder.create_template_folder",
        service_id=sample_service.id,
        _data={"name": "bar", "parent_id": str(parent_folder_id)},
        _expected_status=400,
    )

    assert resp["result"] == "error"
    assert resp["message"] == "parent_id not found"


def test_update_template_folder_name(admin_request, sample_service):
    existing_folder = create_template_folder(sample_service)

    resp = admin_request.post(
        "template_folder.update_template_folder",
        service_id=sample_service.id,
        template_folder_id=existing_folder.id,
        _data={"name": "bar"},
    )

    assert resp["data"]["name"] == "bar"
    assert existing_folder.name == "bar"


def test_update_template_folder_users(admin_request, sample_service):
    existing_folder = create_template_folder(sample_service)
    user_1 = create_user(email="notify_1@digital.cabinet-office.gov.uk")
    user_2 = create_user(email="notify_2@digital.cabinet-office.gov.uk")
    user_3 = create_user(email="notify_3@digital.cabinet-office.gov.uk")
    sample_service.users += [user_1, user_2, user_3]
    assert len(existing_folder.users) == 0
    response_1 = admin_request.post(
        "template_folder.update_template_folder",
        service_id=sample_service.id,
        template_folder_id=existing_folder.id,
        _data={"name": "foo", "users_with_permission": [str(user_1.id)]},
    )

    assert response_1["data"]["users_with_permission"] == [str(user_1.id)]
    assert len(existing_folder.users) == 1

    response_2 = admin_request.post(
        "template_folder.update_template_folder",
        service_id=sample_service.id,
        template_folder_id=existing_folder.id,
        _data={"name": "foo", "users_with_permission": [str(user_2.id), str(user_3.id)]},
    )

    assert set(response_2["data"]["users_with_permission"]) == {str(user_2.id), str(user_3.id)}
    assert len(existing_folder.users) == 2


@pytest.mark.parametrize(
    "data, err",
    [
        ({}, "name is a required property"),
        ({"name": None}, "name None is not of type string"),
        ({"name": ""}, "name  should be non-empty"),
    ],
)
def test_update_template_folder_fails_if_missing_name(admin_request, sample_service, data, err):
    existing_folder = create_template_folder(sample_service)

    resp = admin_request.post(
        "template_folder.update_template_folder",
        service_id=sample_service.id,
        template_folder_id=existing_folder.id,
        _data=data,
        _expected_status=400,
    )

    assert resp == {"status_code": 400, "errors": [{"error": "ValidationError", "message": err}]}


def test_delete_template_folder(admin_request, sample_service):
    existing_folder = create_template_folder(sample_service)

    admin_request.delete(
        "template_folder.delete_template_folder",
        service_id=sample_service.id,
        template_folder_id=existing_folder.id,
    )

    assert TemplateFolder.query.all() == []


def test_delete_template_folder_fails_if_folder_has_subfolders(admin_request, sample_service):
    existing_folder = create_template_folder(sample_service)
    existing_subfolder = create_template_folder(sample_service, parent=existing_folder)  # noqa

    resp = admin_request.delete(
        "template_folder.delete_template_folder",
        service_id=sample_service.id,
        template_folder_id=existing_folder.id,
        _expected_status=400,
    )

    assert resp == {"result": "error", "message": "Folder is not empty"}

    assert TemplateFolder.query.count() == 2


def test_delete_template_folder_fails_if_folder_contains_templates(admin_request, sample_service, sample_template):
    existing_folder = create_template_folder(sample_service)
    sample_template.folder = existing_folder

    resp = admin_request.delete(
        "template_folder.delete_template_folder",
        service_id=sample_service.id,
        template_folder_id=existing_folder.id,
        _expected_status=400,
    )

    assert resp == {"result": "error", "message": "Folder is not empty"}

    assert TemplateFolder.query.count() == 1


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"templates": None, "folders": []},
        {"folders": []},
        {"templates": [], "folders": [None]},
        {"templates": [], "folders": ["not a uuid"]},
    ],
)
def test_move_to_folder_validates_schema(data, admin_request, notify_db_session):
    admin_request.post(
        "template_folder.move_to_template_folder",
        service_id=uuid.uuid4(),
        target_template_folder_id=uuid.uuid4(),
        _data=data,
        _expected_status=400,
    )


def test_move_to_folder_moves_folders_and_templates(admin_request, sample_service):
    target_folder = create_template_folder(sample_service, name="target")
    f1 = create_template_folder(sample_service, name="f1")
    f2 = create_template_folder(sample_service, name="f2")

    t1 = create_template(sample_service, template_name="t1", folder=f1)
    t2 = create_template(sample_service, template_name="t2", folder=f1)
    t3 = create_template(sample_service, template_name="t3", folder=f2)
    t4 = create_template(sample_service, template_name="t4", folder=target_folder)

    admin_request.post(
        "template_folder.move_to_template_folder",
        service_id=sample_service.id,
        target_template_folder_id=target_folder.id,
        _data={"templates": [str(t1.id)], "folders": [str(f1.id)]},
        _expected_status=204,
    )

    assert target_folder.parent is None
    assert f1.parent == target_folder
    assert f2.parent is None  # unchanged

    assert t1.folder == target_folder  # moved out of f1, even though f1 is also being moved
    assert t2.folder == f1  # stays in f1, though f1 has moved
    assert t3.folder == f2  # unchanged
    assert t4.folder == target_folder  # unchanged

    # versions are all unchanged
    assert t1.version == 1
    assert t2.version == 1
    assert t3.version == 1
    assert t4.version == 1


def test_move_to_folder_moves_folders_and_templates_to_top_level_if_no_target(admin_request, sample_service):
    f1 = create_template_folder(sample_service, name="f1")
    f2 = create_template_folder(sample_service, name="f2", parent=f1)

    t1 = create_template(sample_service, template_name="t1", folder=f1)
    t2 = create_template(sample_service, template_name="t2", folder=f1)
    t3 = create_template(sample_service, template_name="t3", folder=f2)

    admin_request.post(
        "template_folder.move_to_template_folder",
        service_id=sample_service.id,
        target_template_folder_id=None,
        _data={"templates": [str(t1.id)], "folders": [str(f2.id)]},
        _expected_status=204,
    )

    assert f1.parent is None  # unchanged
    assert f2.parent is None

    assert t1.folder is None  # moved out of f1
    assert t2.folder == f1  # unchanged
    assert t3.folder == f2  # stayed in f2 even though the parent changed


def test_move_to_folder_rejects_folder_from_other_service(admin_request, notify_db_session):
    s1 = create_service(service_name="s1")
    s2 = create_service(service_name="s2")

    f2 = create_template_folder(s2)

    response = admin_request.post(
        "template_folder.move_to_template_folder",
        service_id=s1.id,
        target_template_folder_id=None,
        _data={"templates": [], "folders": [str(f2.id)]},
        _expected_status=400,
    )
    assert response["message"] == f"No folder found with id {f2.id} for service {s1.id}"


def test_move_to_folder_rejects_template_from_other_service(admin_request, notify_db_session):
    s1 = create_service(service_name="s1")
    s2 = create_service(service_name="s2")

    t2 = create_template(s2)

    response = admin_request.post(
        "template_folder.move_to_template_folder",
        service_id=s1.id,
        target_template_folder_id=None,
        _data={"templates": [str(t2.id)], "folders": []},
        _expected_status=400,
    )
    assert response["message"] == f"Could not move to folder: No template found with id {t2.id} for service {s1.id}"


def test_move_to_folder_rejects_if_it_would_cause_folder_loop(admin_request, sample_service):
    f1 = create_template_folder(sample_service, name="f1")
    target_folder = create_template_folder(sample_service, name="target", parent=f1)

    response = admin_request.post(
        "template_folder.move_to_template_folder",
        service_id=sample_service.id,
        target_template_folder_id=target_folder.id,
        _data={"templates": [], "folders": [str(f1.id)]},
        _expected_status=400,
    )
    assert response["message"] == "You cannot move a folder to one of its subfolders"


def test_move_to_folder_itself_is_rejected(admin_request, sample_service):
    target_folder = create_template_folder(sample_service, name="target")

    response = admin_request.post(
        "template_folder.move_to_template_folder",
        service_id=sample_service.id,
        target_template_folder_id=target_folder.id,
        _data={"templates": [], "folders": [str(target_folder.id)]},
        _expected_status=400,
    )
    assert response["message"] == "You cannot move a folder to itself"


def test_move_to_folder_skips_archived_templates(admin_request, sample_service):
    target_folder = create_template_folder(sample_service)
    other_folder = create_template_folder(sample_service)

    archived_template = create_template(sample_service, archived=True, folder=None)
    unarchived_template = create_template(sample_service, archived=False, folder=other_folder)

    archived_timestamp = archived_template.updated_at

    admin_request.post(
        "template_folder.move_to_template_folder",
        service_id=sample_service.id,
        target_template_folder_id=target_folder.id,
        _data={"templates": [str(archived_template.id), str(unarchived_template.id)], "folders": []},
        _expected_status=204,
    )

    assert archived_template.updated_at == archived_timestamp
    assert archived_template.folder is None
    assert unarchived_template.folder == target_folder
