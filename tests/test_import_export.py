import asyncio
import copy
import datetime
import re
import time
from functools import partial
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import UUID
from uuid import uuid4

import pytest
from fastramqpi.context import Context
from httpx import HTTPStatusError
from ramodels.mo.details.address import Address
from ramodels.mo.details.engagement import Engagement
from ramodels.mo.details.it_system import ITUser
from ramodels.mo.employee import Employee
from ramqp.mo.models import MORoutingKey
from structlog.testing import capture_logs

from mo_ldap_import_export.exceptions import DNNotFound
from mo_ldap_import_export.exceptions import IgnoreChanges
from mo_ldap_import_export.exceptions import NoObjectsReturnedException
from mo_ldap_import_export.exceptions import NotSupportedException
from mo_ldap_import_export.import_export import IgnoreMe
from mo_ldap_import_export.import_export import SyncTool
from mo_ldap_import_export.ldap_classes import LdapObject


@pytest.fixture
def context(
    dataloader: AsyncMock,
    converter: MagicMock,
    export_checks: AsyncMock,
    settings: MagicMock,
) -> Context:
    context = Context(
        {
            "user_context": {
                "dataloader": dataloader,
                "converter": converter,
                "export_checks": export_checks,
                "settings": settings,
            }
        }
    )
    return context


@pytest.fixture
def sync_tool(context: Context) -> SyncTool:
    sync_tool = SyncTool(context)
    return sync_tool


async def test_listen_to_changes_in_org_units(
    converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
):

    org_unit_info = {uuid4(): {"name": "Magenta Aps"}}

    dataloader.load_mo_org_units = MagicMock()
    dataloader.load_mo_org_units.return_value = org_unit_info

    payload = MagicMock()
    payload.uuid = uuid4()

    mo_routing_key = MORoutingKey.build("org_unit.org_unit.edit")

    await sync_tool.listen_to_changes_in_org_units(
        payload,
        routing_key=mo_routing_key,
        delete=False,
        current_objects_only=True,
    )
    assert converter.org_unit_info == org_unit_info


async def test_listen_to_change_in_org_unit_address(
    dataloader: AsyncMock,
    load_settings_overrides: dict[str, str],
    converter: MagicMock,
    sync_tool: SyncTool,
):
    mo_routing_key = MORoutingKey.build("org_unit.address.edit")

    address = Address.from_simplified_fields("foo", uuid4(), "2021-01-01")
    employee1 = Employee(cpr_no="0101011234")
    employee2 = Employee(cpr_no="0101011235")

    load_mo_address = AsyncMock()
    load_mo_employees_in_org_unit = AsyncMock()
    load_mo_org_unit_addresses = AsyncMock()
    modify_ldap_object = AsyncMock()
    modify_ldap_object.return_value = [{"description": "success"}]

    load_mo_address.return_value = address

    # Note: The same employee is linked to this unit twice;
    # The duplicate employee should not be modified twice
    load_mo_employees_in_org_unit.return_value = [employee1, employee1, employee2]
    load_mo_org_unit_addresses.return_value = [address]

    dataloader.modify_ldap_object = modify_ldap_object
    dataloader.load_mo_address = load_mo_address
    dataloader.load_mo_employees_in_org_unit = load_mo_employees_in_org_unit
    dataloader.load_mo_org_unit_addresses = load_mo_org_unit_addresses

    converter.find_ldap_object_class.return_value = "user"

    payload = MagicMock()
    payload.uuid = uuid4()

    # Simulate another employee which is being processed at the exact same time.
    async def employee_in_progress():
        sync_tool.uuids_in_progress.append(employee1.uuid)
        await asyncio.sleep(1)
        sync_tool.uuids_in_progress.remove(employee1.uuid)

    with patch("mo_ldap_import_export.import_export.cleanup", AsyncMock()):
        with capture_logs() as cap_logs:
            await asyncio.gather(
                employee_in_progress(),
                sync_tool.listen_to_changes_in_org_units(
                    payload,
                    routing_key=mo_routing_key,
                    delete=False,
                    current_objects_only=True,
                ),
            )
            messages = [w for w in cap_logs if w["log_level"] == "info"]

            # Validate that listen_to_changes_in_org_units had to wait for
            # employee_in_progress to finish
            assert "in progress" in str(messages)

    # Assert that an address was uploaded to two ldap objects
    # (even though load_mo_employees_in_org_unit returned three employee objects)
    assert modify_ldap_object.await_count == 2

    dataloader.find_or_make_mo_employee_dn.side_effect = DNNotFound("DN not found")

    with capture_logs() as cap_logs:
        await sync_tool.listen_to_changes_in_org_units(
            payload,
            routing_key=mo_routing_key,
            delete=False,
            current_objects_only=True,
        )

        messages = [w for w in cap_logs if w["log_level"] == "info"]

        assert re.match(
            "DN not found",
            messages[-1]["event"].detail,
        )

    dataloader.find_or_make_mo_employee_dn.side_effect = IgnoreChanges("Ignore this")

    with capture_logs() as cap_logs:
        await sync_tool.listen_to_changes_in_org_units(
            payload,
            routing_key=mo_routing_key,
            delete=False,
            current_objects_only=True,
        )

        messages = [w for w in cap_logs if w["log_level"] == "info"]

        assert re.match(
            "Ignore this",
            messages[-1]["event"].detail,
        )


async def test_listen_to_change_in_org_unit_address_not_supported(
    dataloader: AsyncMock,
    load_settings_overrides: dict[str, str],
    converter: MagicMock,
    sync_tool: SyncTool,
):
    """
    Mapping an organization unit address to non-employee objects is not supported.
    """
    mo_routing_key = MORoutingKey.build("org_unit.address.edit")
    payload = MagicMock()
    payload.uuid = uuid4()

    address = Address.from_simplified_fields("foo", uuid4(), "2021-01-01")

    def find_ldap_object_class(json_key):
        d = {"Employee": "user", "LocationUnit": "address"}
        return d[json_key]

    converter.find_ldap_object_class.side_effect = find_ldap_object_class

    load_mo_address = AsyncMock()
    load_mo_address.return_value = address
    dataloader.load_mo_address = load_mo_address

    converter.org_unit_address_type_info = {
        str(address.address_type.uuid): {"user_key": "LocationUnit"}
    }
    converter.get_org_unit_address_type_user_key.return_value = "LocationUnit"

    with pytest.raises(NotSupportedException):
        await sync_tool.listen_to_changes_in_org_units(
            payload,
            routing_key=mo_routing_key,
            delete=False,
            current_objects_only=True,
        )


async def test_listen_to_changes_in_employees(
    dataloader: AsyncMock,
    load_settings_overrides: dict[str, str],
    test_mo_address: Address,
    sync_tool: SyncTool,
    converter: MagicMock,
) -> None:

    settings_mock = MagicMock()
    settings_mock.ldap_search_base = "bar"

    converter.cpr_field = "EmployeeID"
    converted_ldap_object = LdapObject(dn="Foo")
    converter.to_ldap.return_value = converted_ldap_object
    converter.mapping = {"mo_to_ldap": {"EmailEmployee": 2}}
    converter.get_it_system_user_key.return_value = "AD"

    address_type_user_key = "EmailEmployee"
    converter.get_employee_address_type_user_key.return_value = address_type_user_key

    it_system_type_name = "AD"

    payload = MagicMock()
    payload.uuid = uuid4()
    payload.object_uuid = uuid4()

    settings = MagicMock()
    settings.ldap_search_base = "DC=bar"

    # Simulate a created employee
    mo_routing_key = MORoutingKey.build("employee.employee.create")
    with patch("mo_ldap_import_export.import_export.cleanup", AsyncMock()):
        await asyncio.gather(
            sync_tool.listen_to_changes_in_employees(
                payload,
                routing_key=mo_routing_key,
                delete=False,
                current_objects_only=True,
            ),
        )
    assert dataloader.load_mo_employee.called
    assert converter.to_ldap.called
    assert dataloader.modify_ldap_object.called
    dataloader.modify_ldap_object.assert_called_with(
        converted_ldap_object, "Employee", overwrite=True, delete=False
    )
    assert not dataloader.load_mo_address.called

    # Simulate a created address
    mo_routing_key = MORoutingKey.build("employee.address.create")
    with patch("mo_ldap_import_export.import_export.cleanup", AsyncMock()):
        await asyncio.gather(
            sync_tool.listen_to_changes_in_employees(
                payload,
                routing_key=mo_routing_key,
                delete=False,
                current_objects_only=True,
            ),
        )
    assert dataloader.load_mo_address.called
    dataloader.modify_ldap_object.assert_called_with(
        converted_ldap_object, address_type_user_key, delete=False
    )

    # Simulate a created IT user
    mo_routing_key = MORoutingKey.build("employee.it.create")
    with patch("mo_ldap_import_export.import_export.cleanup", AsyncMock()):
        await asyncio.gather(
            sync_tool.listen_to_changes_in_employees(
                payload,
                routing_key=mo_routing_key,
                delete=False,
                current_objects_only=True,
            ),
        )
    assert dataloader.load_mo_it_user.called
    dataloader.modify_ldap_object.assert_called_with(
        converted_ldap_object, it_system_type_name, delete=False
    )

    # Simulate a created engagement
    mo_routing_key = MORoutingKey.build("employee.engagement.create")
    with patch("mo_ldap_import_export.import_export.cleanup", AsyncMock()):
        await asyncio.gather(
            sync_tool.listen_to_changes_in_employees(
                payload,
                routing_key=mo_routing_key,
                delete=False,
                current_objects_only=True,
            ),
        )
    assert dataloader.load_mo_engagement.called
    dataloader.modify_ldap_object.assert_called_with(
        converted_ldap_object, "Engagement", delete=False
    )

    # Simulate an uuid which should be skipped
    # And an uuid which is too old, so it will be removed from the list
    old_uuid = uuid4()
    uuid_which_should_remain = uuid4()

    uuids_to_ignore = IgnoreMe()

    uuids_to_ignore.ignore_dict = {
        # This uuid should be ignored (once)
        str(payload.object_uuid): [datetime.datetime.now(), datetime.datetime.now()],
        # This uuid has been here for too long, and should be removed
        str(old_uuid): [datetime.datetime(2020, 1, 1)],
        # This uuid should remain in the list
        str(uuid_which_should_remain): [datetime.datetime.now()],
    }

    sync_tool.uuids_to_ignore = uuids_to_ignore

    with capture_logs() as cap_logs:
        with pytest.raises(IgnoreChanges, match=f".*Ignoring .*{payload.object_uuid}"):
            await asyncio.gather(
                sync_tool.listen_to_changes_in_employees(
                    payload,
                    routing_key=mo_routing_key,
                    delete=False,
                    current_objects_only=True,
                ),
            )

        entries = [w for w in cap_logs if w["log_level"] == "info"]

        assert re.match(
            f"Removing .* belonging to {old_uuid} from ignore_dict",
            entries[3]["event"],
        )
        assert len(uuids_to_ignore) == 2  # Note that the old_uuid is removed by clean()
        assert len(uuids_to_ignore[old_uuid]) == 0
        assert len(uuids_to_ignore[uuid_which_should_remain]) == 1
        assert len(uuids_to_ignore[payload.object_uuid]) == 1


async def test_listen_to_changes_in_employees_no_dn(
    dataloader: AsyncMock,
    load_settings_overrides: dict[str, str],
    test_mo_address: Address,
    sync_tool: SyncTool,
    converter: MagicMock,
) -> None:
    payload = MagicMock()
    mo_routing_key = MORoutingKey.build("employee.employee.create")
    dataloader.find_or_make_mo_employee_dn.side_effect = DNNotFound("Not found")

    with capture_logs() as cap_logs:
        await asyncio.gather(
            sync_tool.listen_to_changes_in_employees(
                payload,
                routing_key=mo_routing_key,
                delete=False,
                current_objects_only=True,
            ),
        )

        messages = [w for w in cap_logs if w["log_level"] == "info"]
        assert re.match(
            "DN not found.",
            messages[-1]["event"],
        )


async def test_format_converted_engagement_objects(
    converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
):

    converter.get_mo_attributes.return_value = ["user_key", "job_function"]
    converter.find_mo_object_class.return_value = "Engagement"
    converter.import_mo_object_class.return_value = Engagement

    employee_uuid = uuid4()

    engagement1 = Engagement.from_simplified_fields(
        org_unit_uuid=uuid4(),
        person_uuid=employee_uuid,
        job_function_uuid=uuid4(),
        engagement_type_uuid=uuid4(),
        user_key="123",
        from_date="2020-01-01",
    )

    engagement2 = Engagement.from_simplified_fields(
        org_unit_uuid=uuid4(),
        person_uuid=employee_uuid,
        job_function_uuid=uuid4(),
        engagement_type_uuid=uuid4(),
        user_key="foo",
        from_date="2021-01-01",
    )

    # We do not expect this one the be uploaded, because its user_key exists twice in MO
    engagement3 = Engagement.from_simplified_fields(
        org_unit_uuid=uuid4(),
        person_uuid=employee_uuid,
        job_function_uuid=uuid4(),
        engagement_type_uuid=uuid4(),
        user_key="duplicate_key",
        from_date="2021-01-01",
    )

    engagement1_in_mo = Engagement.from_simplified_fields(
        org_unit_uuid=uuid4(),
        person_uuid=employee_uuid,
        job_function_uuid=uuid4(),
        engagement_type_uuid=uuid4(),
        user_key="123",
        from_date="2021-01-01",
    )

    engagement2_in_mo = Engagement.from_simplified_fields(
        org_unit_uuid=uuid4(),
        person_uuid=employee_uuid,
        job_function_uuid=uuid4(),
        engagement_type_uuid=uuid4(),
        user_key="duplicate_key",
        from_date="2021-01-01",
    )

    engagement3_in_mo = Engagement.from_simplified_fields(
        org_unit_uuid=uuid4(),
        person_uuid=employee_uuid,
        job_function_uuid=uuid4(),
        engagement_type_uuid=uuid4(),
        user_key="duplicate_key",
        from_date="2021-01-01",
    )

    dataloader.load_mo_employee_engagements.return_value = [
        engagement1_in_mo,
        engagement2_in_mo,
        engagement3_in_mo,
    ]

    json_key = "Engagement"

    converted_objects = [engagement1, engagement2, engagement3]

    formatted_objects = await sync_tool.format_converted_objects(
        converted_objects,
        json_key,
    )

    assert len(formatted_objects) == 2
    assert engagement3 not in formatted_objects
    assert formatted_objects[1] == engagement2
    assert formatted_objects[0].uuid == engagement1_in_mo.uuid
    assert formatted_objects[0].user_key == engagement1.user_key


async def test_format_converted_employee_objects(
    converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
):

    converter.find_mo_object_class.return_value = "Employee"

    employee1 = Employee(cpr_no="1212121234")
    employee2 = Employee(cpr_no="1212121235")

    converted_objects = [employee1, employee2]

    formatted_objects = await sync_tool.format_converted_objects(
        converted_objects, "Employee"
    )

    assert formatted_objects[0] == employee1
    assert formatted_objects[1] == employee2


async def test_format_converted_employee_address_objects(
    converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
):

    converter.get_mo_attributes.return_value = ["value", "address_type"]
    converter.find_mo_object_class.return_value = "Address"
    converter.import_mo_object_class.return_value = Address

    person_uuid = uuid4()
    address1 = Address.from_simplified_fields(
        "foo", uuid4(), "2021-01-01", person_uuid=person_uuid
    )
    address2 = Address.from_simplified_fields(
        "bar", uuid4(), "2021-01-01", person_uuid=person_uuid
    )

    address1_in_mo = Address.from_simplified_fields(
        "foo", uuid4(), "2021-01-01", person_uuid=person_uuid
    )

    converted_objects = [address1, address2]

    dataloader.load_mo_employee_addresses.return_value = [address1_in_mo]

    formatted_objects = await sync_tool.format_converted_objects(
        converted_objects,
        "Address",
    )

    assert formatted_objects[1] == address2

    assert formatted_objects[0].uuid == address1_in_mo.uuid
    assert formatted_objects[0].value == "foo"

    # Simulate that a matching employee for this address does not exist
    dataloader.load_mo_employee_addresses.side_effect = NoObjectsReturnedException("f")
    with pytest.raises(NoObjectsReturnedException):
        await sync_tool.format_converted_objects(converted_objects, "Address")


async def test_format_converted_org_unit_address_objects(
    converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
):

    converter.get_mo_attributes.return_value = ["value", "address_type"]
    converter.find_mo_object_class.return_value = "Address"
    converter.import_mo_object_class.return_value = Address

    org_unit_uuid = uuid4()
    address1 = Address.from_simplified_fields(
        "foo", uuid4(), "2021-01-01", org_unit_uuid=org_unit_uuid
    )
    address2 = Address.from_simplified_fields(
        "bar", uuid4(), "2021-01-01", org_unit_uuid=org_unit_uuid
    )

    address1_in_mo = Address.from_simplified_fields(
        "foo", uuid4(), "2021-01-01", org_unit_uuid=org_unit_uuid
    )

    converted_objects = [address1, address2]

    dataloader.load_mo_org_unit_addresses.return_value = [address1_in_mo]

    formatted_objects = await sync_tool.format_converted_objects(
        converted_objects,
        "Address",
    )

    assert formatted_objects[1] == address2

    assert formatted_objects[0].uuid == address1_in_mo.uuid
    assert formatted_objects[0].value == "foo"

    # Simulate that a matching org unit for this address does not exist
    dataloader.load_mo_org_unit_addresses.side_effect = NoObjectsReturnedException("f")
    with pytest.raises(NoObjectsReturnedException):
        await sync_tool.format_converted_objects(converted_objects, "Address")


async def test_format_converted_org_unit_address_objects_identical_to_mo(
    converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
):

    converter.get_mo_attributes.return_value = ["value", "address_type"]
    converter.find_mo_object_class.return_value = "Address"
    converter.import_mo_object_class.return_value = Address

    org_unit_uuid = uuid4()
    address_type_uuid = uuid4()
    address1 = Address.from_simplified_fields(
        "foo", address_type_uuid, "2021-01-01", org_unit_uuid=org_unit_uuid
    )
    address2 = Address.from_simplified_fields(
        "bar", address_type_uuid, "2021-01-01", org_unit_uuid=org_unit_uuid
    )

    # This one is identical to the one which we are trying to upload
    address1_in_mo = Address.from_simplified_fields(
        "foo", address_type_uuid, "2021-01-01", org_unit_uuid=org_unit_uuid
    )

    converted_objects = [address1, address2]

    dataloader.load_mo_org_unit_addresses.return_value = [address1_in_mo]

    formatted_objects = await sync_tool.format_converted_objects(
        converted_objects,
        "Address",
    )

    assert formatted_objects[0].value == "bar"
    assert len(formatted_objects) == 1


async def test_format_converted_address_objects_without_person_or_org_unit(
    converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
):

    converter.get_mo_attributes.return_value = ["value", "address_type"]
    converter.find_mo_object_class.return_value = "Address"
    converter.import_mo_object_class.return_value = Address

    # These addresses have neither an org unit uuid or person uuid. we cannot convert
    # them
    address_type_uuid = uuid4()
    address1 = Address.from_simplified_fields("foo", address_type_uuid, "2021-01-01")
    address2 = Address.from_simplified_fields("bar", address_type_uuid, "2021-01-01")

    converted_objects = [address1, address2]

    formatted_objects = await sync_tool.format_converted_objects(
        converted_objects,
        "Address",
    )

    assert len(formatted_objects) == 0


async def test_format_converted_it_user_objects(
    converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
):
    converter.get_mo_attributes.return_value = ["value", "address_type"]
    converter.find_mo_object_class.return_value = "ITUser"
    converter.import_mo_object_class.return_value = ITUser

    it_user_in_mo = ITUser.from_simplified_fields(
        "Username1", uuid4(), "2021-01-01", person_uuid=uuid4()
    )

    dataloader.load_mo_employee_it_users.return_value = [it_user_in_mo]

    converted_objects = [
        ITUser.from_simplified_fields(
            "Username1", uuid4(), "2021-01-01", person_uuid=uuid4()
        ),
        ITUser.from_simplified_fields(
            "Username2", uuid4(), "2021-01-01", person_uuid=uuid4()
        ),
    ]

    formatted_objects = await sync_tool.format_converted_objects(
        converted_objects,
        "ITUser",
    )

    formatted_user_keys = [f.user_key for f in formatted_objects]
    assert "Username1" not in formatted_user_keys
    assert "Username2" in formatted_user_keys
    assert len(formatted_objects) == 1

    # Simulate that a matching employee for this it user does not exist
    dataloader.load_mo_employee_it_users.side_effect = NoObjectsReturnedException("f")
    with pytest.raises(NoObjectsReturnedException):
        await sync_tool.format_converted_objects(converted_objects, "ITUser")


async def test_format_converted_primary_engagement_objects(
    converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
):

    employee_uuid = uuid4()
    primary_uuid = uuid4()
    engagement1_in_mo_uuid = uuid4()
    engagement2_in_mo_uuid = uuid4()

    converter.get_mo_attributes.return_value = ["user_key", "job_function"]
    converter.find_mo_object_class.return_value = "Engagement"
    converter.import_mo_object_class.return_value = Engagement

    def is_primary(uuid):
        if uuid == engagement1_in_mo_uuid:
            return True
        else:
            return False

    dataloader.is_primary.side_effect = is_primary

    engagement1 = Engagement.from_simplified_fields(
        org_unit_uuid=uuid4(),
        person_uuid=employee_uuid,
        job_function_uuid=uuid4(),
        engagement_type_uuid=uuid4(),
        user_key="123",
        from_date="2020-01-01",
    )

    engagement1_in_mo = Engagement.from_simplified_fields(
        org_unit_uuid=uuid4(),
        person_uuid=employee_uuid,
        job_function_uuid=uuid4(),
        engagement_type_uuid=uuid4(),
        user_key="123",
        from_date="2021-01-01",
        primary_uuid=primary_uuid,
        uuid=engagement1_in_mo_uuid,
    )

    # Engagement with the same user key. We should not update this one because it is
    # not primary.
    engagement2_in_mo = Engagement.from_simplified_fields(
        org_unit_uuid=uuid4(),
        person_uuid=employee_uuid,
        job_function_uuid=uuid4(),
        engagement_type_uuid=uuid4(),
        user_key="123",
        from_date="2021-01-01",
        primary_uuid=None,
        uuid=engagement2_in_mo_uuid,
    )

    dataloader.load_mo_employee_engagements.return_value = [
        engagement1_in_mo,
        engagement2_in_mo,
    ]

    json_key = "Engagement"

    converted_objects = [engagement1]

    formatted_objects = await sync_tool.format_converted_objects(
        converted_objects,
        json_key,
    )

    assert len(formatted_objects) == 1
    assert formatted_objects[0].primary.uuid is not None
    assert formatted_objects[0].user_key == "123"

    # Simulate that a matching employee for this engagement does not exist
    dataloader.load_mo_employee_engagements.side_effect = NoObjectsReturnedException(
        "f"
    )
    with pytest.raises(NoObjectsReturnedException):
        await sync_tool.format_converted_objects(converted_objects, json_key)


async def test_import_single_object_from_LDAP_ignore_twice(
    converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
) -> None:
    """
    When an uuid already is in the uuids_to_ignore dict, it should be added once more
    so it is ignored twice.
    """

    uuid = uuid4()
    mo_object_mock = MagicMock
    mo_object_mock.uuid = uuid
    converter.from_ldap.return_value = [mo_object_mock]

    uuids_to_ignore = IgnoreMe()
    uuids_to_ignore.ignore_dict = {str(uuid): [datetime.datetime.now()]}
    sync_tool.uuids_to_ignore = uuids_to_ignore

    await asyncio.gather(sync_tool.import_single_user("CN=foo"))
    assert len(sync_tool.uuids_to_ignore[uuid]) == 2


async def test_import_single_object_from_LDAP_ignore_dn(
    converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
) -> None:
    dn_to_ignore = "CN=foo"
    ldap_object = LdapObject(dn=dn_to_ignore)
    dataloader.load_ldap_object.return_value = ldap_object
    sync_tool.dns_to_ignore.add(dn_to_ignore)

    with capture_logs() as cap_logs:
        await asyncio.gather(sync_tool.import_single_user("CN=foo"))

        messages = [w for w in cap_logs if w["log_level"] == "info"]
        assert re.match(
            f"\\[check_ignore_dict\\] Ignoring {dn_to_ignore.lower()}",
            messages[-1]["event"].detail,
        )


async def test_import_single_object_from_LDAP_but_import_equals_false(
    converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
):
    converter.__import_to_mo__.return_value = False

    with capture_logs() as cap_logs:
        await asyncio.gather(sync_tool.import_single_user("CN=foo"))

        messages = [w for w in cap_logs if w["log_level"] == "info"]
        for message in messages[1:]:
            assert re.match(
                "__import_to_mo__ == False",
                message["event"],
            )


async def test_import_address_objects(
    context: Context, converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
):
    converter.find_mo_object_class.return_value = "ramodels.mo.details.address.Address"
    converter.import_mo_object_class.return_value = Address
    converter.get_mo_attributes.return_value = ["value", "uuid", "validity"]

    address_type_uuid = uuid4()
    person_uuid = uuid4()

    converted_objects = [
        Address.from_simplified_fields(
            "foo@bar.dk", address_type_uuid, "2021-01-01", person_uuid=person_uuid
        ),
        Address.from_simplified_fields(
            "foo2@bar.dk", address_type_uuid, "2021-01-01", person_uuid=person_uuid
        ),
        Address.from_simplified_fields(
            "foo3@bar.dk", address_type_uuid, "2021-01-01", person_uuid=person_uuid
        ),
    ]

    converter.from_ldap.return_value = converted_objects

    with patch(
        "mo_ldap_import_export.import_export.SyncTool.format_converted_objects",
        return_value=converted_objects,
    ):
        await asyncio.gather(sync_tool.import_single_user("CN=foo"))
        dataloader.upload_mo_objects.assert_called_with(converted_objects)

    with patch(
        "mo_ldap_import_export.import_export.SyncTool.format_converted_objects",
        side_effect=NoObjectsReturnedException("foo"),
    ):
        with capture_logs() as cap_logs:
            await asyncio.gather(sync_tool.import_single_user("CN=foo"))

            messages = [w for w in cap_logs if w["log_level"] == "info"]
            assert "Could not format converted objects. Moving on." in str(messages)

    # Simulate invalid phone number
    dataloader.upload_mo_objects.side_effect = HTTPStatusError(
        "invalid phone number", request=MagicMock(), response=MagicMock()
    )
    with capture_logs() as cap_logs:
        ignore_dict = copy.deepcopy(sync_tool.uuids_to_ignore.ignore_dict)
        await asyncio.gather(sync_tool.import_single_user("CN=foo"))

        messages = [w for w in cap_logs if w["log_level"] == "warning"]
        assert "invalid phone number" in str(messages)

        # Make sure that no uuids are added to the ignore dict, if the import fails
        assert ignore_dict == sync_tool.uuids_to_ignore.ignore_dict


async def test_import_it_user_objects(
    context: Context, converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
):
    converter.find_mo_object_class.return_value = "ramodels.mo.details.address.ITUser"
    converter.import_mo_object_class.return_value = ITUser
    converter.get_mo_attributes.return_value = ["user_key", "validity"]

    it_system_type1_uuid = uuid4()
    it_system_type2_uuid = uuid4()
    person_uuid = uuid4()

    converted_objects = [
        ITUser.from_simplified_fields(
            "Username1", it_system_type1_uuid, "2021-01-01", person_uuid=person_uuid
        ),
        ITUser.from_simplified_fields(
            "Username2", it_system_type2_uuid, "2021-01-01", person_uuid=person_uuid
        ),
        ITUser.from_simplified_fields(
            "Username3", it_system_type2_uuid, "2021-01-01", person_uuid=person_uuid
        ),
    ]

    converter.from_ldap.return_value = converted_objects

    it_user_in_mo = ITUser.from_simplified_fields(
        "Username1", it_system_type1_uuid, "2021-01-01", person_uuid=person_uuid
    )

    it_users_in_mo = [it_user_in_mo]

    dataloader.load_mo_employee_it_users.return_value = it_users_in_mo

    await asyncio.gather(sync_tool.import_single_user("CN=foo"))

    non_existing_converted_objects = [
        converted_objects[1],
        converted_objects[2],
    ]

    dataloader.upload_mo_objects.assert_called_with(non_existing_converted_objects)


async def test_import_single_object_from_LDAP_non_existing_employee(
    context: Context, converter: MagicMock, dataloader: AsyncMock, sync_tool: SyncTool
) -> None:
    dataloader.find_mo_employee_uuid.return_value = None
    await asyncio.gather(sync_tool.import_single_user("CN=foo"))

    # Even though find_mo_employee_uuid does not return an uuid; it is generated
    assert type(converter.from_ldap.call_args_list[0].kwargs["employee_uuid"]) is UUID


async def test_ignoreMe():

    # Initialize empty ignore dict
    strings_to_ignore = IgnoreMe()
    assert len(strings_to_ignore) == 0

    # Add a string which should be ignored
    strings_to_ignore.add("ignore_me")
    assert len(strings_to_ignore) == 1
    assert len(strings_to_ignore["ignore_me"]) == 1

    # Raise an ignore exception so the string gets removed
    with pytest.raises(IgnoreChanges):
        strings_to_ignore.check("ignore_me")
    assert len(strings_to_ignore["ignore_me"]) == 0

    # Add an out-dated entry
    strings_to_ignore.ignore_dict = {
        "old_ignore_string": [datetime.datetime(1900, 1, 1)]
    }
    assert len(strings_to_ignore) == 1
    assert len(strings_to_ignore["old_ignore_string"]) == 1

    # Validate that it is gone after we clean
    strings_to_ignore.clean()
    assert len(strings_to_ignore) == 0
    assert len(strings_to_ignore["old_ignore_string"]) == 0

    # Add multiple out-dated entries
    strings_to_ignore.ignore_dict = {
        "old_ignore_string": [
            datetime.datetime(1900, 1, 1),
            datetime.datetime(1901, 1, 1),
            datetime.datetime(1902, 1, 1),
        ]
    }
    assert len(strings_to_ignore) == 1
    assert len(strings_to_ignore["old_ignore_string"]) == 3

    # Validate that they are all gone after we clean
    strings_to_ignore.clean()
    assert len(strings_to_ignore) == 0
    assert len(strings_to_ignore["old_ignore_string"]) == 0


async def test_remove_from_ignoreMe():

    # Initialize empty ignore dict
    strings_to_ignore = IgnoreMe()

    uuid = uuid4()
    strings_to_ignore.add(uuid)
    strings_to_ignore.add(uuid)

    timestamps = strings_to_ignore[uuid]

    assert len(strings_to_ignore[uuid]) == 2

    strings_to_ignore.remove(uuid)
    assert len(strings_to_ignore[uuid]) == 1
    assert strings_to_ignore[uuid][0] == min(timestamps)

    strings_to_ignore.remove(uuid)
    assert len(strings_to_ignore[uuid]) == 0


async def test_wait_for_export_to_finish(sync_tool: SyncTool):

    wait_for_export_to_finish = partial(
        sync_tool.wait_for_export_to_finish, sleep_time=0.1
    )

    @wait_for_export_to_finish
    async def decorated_func(self, payload):
        await asyncio.sleep(0.2)
        return

    async def regular_func(self, payload):
        await asyncio.sleep(0.2)
        return

    payload = MagicMock()
    payload.uuid = uuid4()

    different_payload = MagicMock()
    different_payload.uuid = uuid4()

    # Normally this would execute in 0.2 seconds + overhead
    t1 = time.time()
    await asyncio.gather(
        regular_func(sync_tool, payload),
        regular_func(sync_tool, payload),
    )
    t2 = time.time()

    elapsed_time = t2 - t1

    assert elapsed_time >= 0.2
    assert elapsed_time < 0.3

    # But the decorator will make the second call wait for the first one to complete
    t1 = time.time()
    await asyncio.gather(
        decorated_func(sync_tool, payload),
        decorated_func(sync_tool, payload),
    )
    t2 = time.time()

    elapsed_time = t2 - t1

    assert elapsed_time >= 0.4
    assert elapsed_time < 0.5

    # But only if payload.uuid is the same in both calls
    t1 = time.time()
    await asyncio.gather(
        decorated_func(sync_tool, payload),
        decorated_func(sync_tool, different_payload),
    )
    t2 = time.time()

    elapsed_time = t2 - t1

    assert elapsed_time >= 0.2
    assert elapsed_time < 0.3


def test_cleanup_needed(sync_tool: SyncTool):
    assert sync_tool.cleanup_needed([{"description": "success"}]) is True
    assert sync_tool.cleanup_needed([{"description": "PermissionDenied"}]) is False
    assert sync_tool.cleanup_needed([None]) is False


async def test_wait_for_import_to_finish(sync_tool: SyncTool):

    wait_for_import_to_finish = partial(
        sync_tool.wait_for_import_to_finish, sleep_time=0.1
    )

    @wait_for_import_to_finish
    async def decorated_func(self, dn):
        await asyncio.sleep(0.2)
        return

    async def regular_func(self, dn):
        await asyncio.sleep(0.2)
        return

    dn = "CN=foo"
    different_dn = "CN=bar"

    # Normally this would execute in 0.2 seconds + overhead
    t1 = time.time()
    await asyncio.gather(
        regular_func(sync_tool, dn),
        regular_func(sync_tool, dn),
    )
    t2 = time.time()

    elapsed_time = t2 - t1

    assert elapsed_time >= 0.2
    assert elapsed_time < 0.3

    # But the decorator will make the second call wait for the first one to complete
    t1 = time.time()
    await asyncio.gather(
        decorated_func(sync_tool, dn),
        decorated_func(sync_tool, dn),
    )
    t2 = time.time()

    elapsed_time = t2 - t1

    assert elapsed_time >= 0.4
    assert elapsed_time < 0.5

    # But only if payload.uuid is the same in both calls
    t1 = time.time()
    await asyncio.gather(
        decorated_func(sync_tool, dn),
        decorated_func(sync_tool, different_dn),
    )
    t2 = time.time()

    elapsed_time = t2 - t1

    assert elapsed_time >= 0.2
    assert elapsed_time < 0.3
