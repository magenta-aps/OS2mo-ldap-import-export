# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=protected-access
import asyncio
import datetime
import re
import time
from collections.abc import Collection
from collections.abc import Iterator
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import UUID
from uuid import uuid4

import pytest
from fastramqpi.context import Context
from gql import gql
from gql.transport.exceptions import TransportQueryError
from graphql import print_ast
from ldap3.core.exceptions import LDAPInvalidValueError
from ramodels.mo._shared import EngagementRef
from ramodels.mo.details.address import Address
from ramodels.mo.details.it_system import ITUser
from ramodels.mo.employee import Employee
from structlog.testing import capture_logs

from mo_ldap_import_export.config import Settings
from mo_ldap_import_export.dataloaders import DataLoader
from mo_ldap_import_export.dataloaders import LdapObject
from mo_ldap_import_export.dataloaders import Verb
from mo_ldap_import_export.exceptions import AttributeNotFound
from mo_ldap_import_export.exceptions import DNNotFound
from mo_ldap_import_export.exceptions import InvalidChangeDict
from mo_ldap_import_export.exceptions import InvalidQueryResponse
from mo_ldap_import_export.exceptions import MultipleObjectsReturnedException
from mo_ldap_import_export.exceptions import NoObjectsReturnedException
from mo_ldap_import_export.exceptions import NotEnabledException
from mo_ldap_import_export.exceptions import UUIDNotFoundException
from mo_ldap_import_export.import_export import IgnoreMe
from mo_ldap_import_export.utils import extract_ou_from_dn


@pytest.fixture()
def ldap_attributes() -> dict:
    return {
        "department": None,
        "name": "John",
        "employeeID": "0101011234",
        "postalAddress": "foo",
    }


@pytest.fixture
def cpr_field() -> str:
    return "employeeID"


@pytest.fixture
def ldap_connection(ldap_attributes: dict) -> Iterator[MagicMock]:
    """Fixture to construct a mock ldap_connection.

    Yields:
        A mock for ldap_connection.
    """

    with patch(
        "mo_ldap_import_export.dataloaders.get_ldap_attributes",
        return_value=ldap_attributes.keys(),
    ):
        ldap_connection = MagicMock()
        ldap_connection.compare.return_value = False
        yield ldap_connection


@pytest.fixture
def legacy_graphql_session() -> Iterator[AsyncMock]:
    yield AsyncMock()


@pytest.fixture
def legacy_model_client() -> Iterator[AsyncMock]:
    yield AsyncMock()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "CONVERSION_MAPPING",
        '{"ldap_to_mo": {}, "mo_to_ldap": {}, "username_generator": {}}',
    )
    monkeypatch.setenv("CLIENT_ID", "foo")
    monkeypatch.setenv("CLIENT_SECRET", "bar")
    monkeypatch.setenv("LDAP_CONTROLLERS", '[{"host": "0.0.0.0"}]')
    monkeypatch.setenv("LDAP_DOMAIN", "LDAP")
    monkeypatch.setenv("LDAP_USER", "foo")
    monkeypatch.setenv("LDAP_PASSWORD", "bar")
    monkeypatch.setenv("LDAP_SEARCH_BASE", "DC=ad,DC=addev")
    monkeypatch.setenv("DEFAULT_ORG_UNIT_LEVEL", "foo")
    monkeypatch.setenv("DEFAULT_ORG_UNIT_TYPE", "foo")
    monkeypatch.setenv("LDAP_OUS_TO_WRITE_TO", '[""]')
    monkeypatch.setenv("FASTRAMQPI__AMQP__URL", "amqp://guest:guest@msg_broker:5672/")
    monkeypatch.setenv("INTERNAL_AMQP__URL", "amqp://guest:guest@msg_broker:5672/")

    return Settings()


@pytest.fixture
def converter() -> MagicMock:
    converter_mock = MagicMock()
    converter_mock.find_ldap_object_class.return_value = "user"
    converter_mock._export_to_ldap_ = MagicMock()
    converter_mock._export_to_ldap_.return_value = True
    return converter_mock


@pytest.fixture
def username_generator() -> MagicMock:
    return AsyncMock()


@pytest.fixture
def sync_tool() -> AsyncMock:
    sync_tool = AsyncMock()
    sync_tool.dns_to_ignore = IgnoreMe()
    return sync_tool


@pytest.fixture
def context(
    ldap_connection: MagicMock,
    legacy_graphql_session: AsyncMock,
    legacy_model_client: AsyncMock,
    settings: Settings,
    cpr_field: str,
    converter: MagicMock,
    sync_tool: AsyncMock,
    username_generator: MagicMock,
) -> Context:
    return {
        "legacy_graphql_session": legacy_graphql_session,
        "legacy_model_client": legacy_model_client,
        "user_context": {
            "settings": settings,
            "ldap_connection": ldap_connection,
            "cpr_field": cpr_field,
            "converter": converter,
            "sync_tool": sync_tool,
            "username_generator": username_generator,
            "ldap_it_system_user_key": "Active Directory",
        },
    }


@pytest.fixture
def get_attribute_types() -> dict:
    attr1_mock = MagicMock()
    attr2_mock = MagicMock()
    attr1_mock.single_value = False
    attr2_mock.single_value = True
    attr1_mock.syntax = "1.3.6.1.4.1.1466.115.121.1.7"  # Boolean
    attr2_mock.syntax = "1.3.6.1.4.1.1466.115.121.1.27"  # Integer
    return {
        "attr1": attr1_mock,
        "attr2": attr2_mock,
        "department": MagicMock(),
        "name": MagicMock(),
        "employeeID": MagicMock(),
        "postalAddress": MagicMock(),
        "objectClass": MagicMock(),
    }


@pytest.fixture
def dataloader(context: Context, get_attribute_types: dict) -> DataLoader:
    """Fixture to construct a dataloaders object using fixture mocks.

    Yields:
        Dataloaders with mocked clients.
    """
    with patch(
        "mo_ldap_import_export.dataloaders.get_attribute_types",
        return_value=get_attribute_types,
    ):
        return DataLoader(context)


def mock_ldap_response(ldap_attributes: dict, dn: str) -> dict[str, Collection[str]]:
    expected_attributes = ldap_attributes.keys()
    inner_dict = ldap_attributes

    for attribute in expected_attributes:
        if attribute not in inner_dict.keys():
            inner_dict[attribute] = None

    response = {"dn": dn, "type": "searchResEntry", "attributes": inner_dict}

    return response


async def test_load_ldap_cpr_object(
    ldap_connection: MagicMock, dataloader: DataLoader, ldap_attributes: dict
) -> None:
    # Mock data
    dn = "CN=Nick Janssen,OU=Users,OU=Magenta,DC=ad,DC=addev"

    expected_result = LdapObject(dn=dn, **ldap_attributes)
    ldap_connection.response = [mock_ldap_response(ldap_attributes, dn)]

    output = await dataloader.load_ldap_cpr_object("0101012002", "Employee")
    assert output == expected_result

    with pytest.raises(NoObjectsReturnedException):
        await dataloader.load_ldap_cpr_object("None", "Employee")

    with pytest.raises(NoObjectsReturnedException):
        dataloader.user_context["cpr_field"] = None
        await dataloader.load_ldap_cpr_object("0101012002", "Employee")


async def test_load_ldap_objects(
    ldap_connection: MagicMock, dataloader: DataLoader, ldap_attributes: dict
) -> None:
    dn = "CN=Nick Janssen,OU=Users,OU=Magenta,DC=ad,DC=addev"
    expected_result = [LdapObject(dn=dn, **ldap_attributes)] * 2
    ldap_connection.response = [mock_ldap_response(ldap_attributes, dn)] * 2

    output = await asyncio.gather(
        dataloader.load_ldap_objects("Employee"),
    )

    assert output[0] == expected_result


async def test_load_ldap_OUs(ldap_connection: MagicMock, dataloader: DataLoader):
    group_dn1 = "OU=Users,OU=Magenta,DC=ad,DC=addev"
    group_dn2 = "OU=Groups,OU=Magenta,DC=ad,DC=addev"
    ou1 = extract_ou_from_dn(group_dn1)
    ou2 = extract_ou_from_dn(group_dn2)
    user_dn = "CN=Nick Janssen,OU=Users,OU=Magenta,DC=ad,DC=addev"

    first_response = [
        mock_ldap_response({}, group_dn1),
        mock_ldap_response({}, group_dn2),
    ]

    second_response = [mock_ldap_response({}, user_dn)]
    third_response: list = []

    responses = iter(
        [
            first_response,
            second_response,
            third_response,
        ]
    )

    def set_new_result(*args, **kwargs) -> None:
        ldap_connection.response = next(responses)

    ldap_connection.search.side_effect = set_new_result

    output = dataloader.load_ldap_OUs(None)

    assert ou1 in output
    assert ou2 in output
    assert output[ou1]["empty"] is False
    assert output[ou2]["empty"] is True


async def test_modify_ldap_employee(
    ldap_connection: MagicMock,
    dataloader: DataLoader,
    ldap_attributes: dict,
) -> None:
    employee = LdapObject(
        dn="CN=Nick Janssen,OU=Users,OU=Magenta,DC=ad,DC=addev",
        **ldap_attributes,
    )

    bad_response = {
        "result": 67,
        "description": "notAllowedOnRDN",
        "dn": "",
        "message": (
            "000020B1: UpdErr: DSID-030F1357,"
            " problem 6004 (CANT_ON_RDN), data 0\n\x00"
        ),
        "referrals": None,
        "type": "modifyResponse",
    }
    good_response = {
        "result": 0,
        "description": "success",
        "dn": "",
        "message": "",
        "referrals": None,
        "type": "modifyResponse",
    }

    # LDAP does not allow one to change the 'name' attribute and throws a bad response
    not_allowed_on_RDN = ["name"]
    parameters_to_upload = [k for k in employee.dict().keys() if k not in ["dn", "cpr"]]
    allowed_parameters_to_upload = [
        p for p in parameters_to_upload if p not in not_allowed_on_RDN
    ]
    disallowed_parameters_to_upload = [
        p for p in parameters_to_upload if p not in allowed_parameters_to_upload
    ]

    results = iter(
        [good_response] * len(allowed_parameters_to_upload)
        + [bad_response] * len(disallowed_parameters_to_upload)
    )

    def set_new_result(*args, **kwargs) -> None:
        ldap_connection.result = next(results)

    # Every time a modification is performed, point to the next page.
    ldap_connection.modify.side_effect = set_new_result

    # Get result from dataloader
    with patch(
        "mo_ldap_import_export.dataloaders.DataLoader.load_ldap_cpr_object",
        return_value=employee,
    ):
        output = await asyncio.gather(
            dataloader.modify_ldap_object(employee, "user"),
        )

    assert output == [
        [good_response] * len(allowed_parameters_to_upload)
        + [bad_response] * len(disallowed_parameters_to_upload)
    ]


async def test_append_data_to_ldap_object(
    ldap_connection: MagicMock,
    dataloader: DataLoader,
    ldap_attributes: dict,
    cpr_field: str,
):
    address = LdapObject(
        dn="CN=Nick Janssen,OU=Users,OU=Magenta,DC=ad,DC=addev",
        postalAddress="foo",
        **{cpr_field: "123"},
    )

    dataloader.single_value = {"postalAddress": False, cpr_field: True}

    await asyncio.gather(
        dataloader.modify_ldap_object(address, "user"),
    )

    changes = {"postalAddress": [("MODIFY_ADD", "foo")]}
    dn = address.dn
    assert ldap_connection.modify.called_once_with(dn, changes)


async def test_delete_data_from_ldap_object(
    ldap_connection: MagicMock,
    dataloader: DataLoader,
    ldap_attributes: dict,
    cpr_field: str,
):
    address = LdapObject(
        dn="CN=Nick Janssen,OU=Users,OU=Magenta,DC=ad,DC=addev",
        postalAddress="foo",
        sharedValue="bar",
        **{cpr_field: "123"},
    )

    dataloader.single_value = {"postalAddress": False, cpr_field: True}

    # Note: 'sharedValue' won't be deleted because it is shared with another ldap object
    dataloader._mo_to_ldap_attributes = [
        "postalAddress",
        cpr_field,
        cpr_field,
        "sharedValue",
        "sharedValue",
    ]

    await asyncio.gather(
        dataloader.modify_ldap_object(address, "user", delete=True),
    )

    changes = {"postalAddress": [("MODIFY_DELETE", "foo")]}
    dn = address.dn
    assert ldap_connection.modify.called_once_with(dn, changes)


async def test_upload_ldap_object_invalid_value(
    ldap_connection: MagicMock,
    dataloader: DataLoader,
    cpr_field: str,
):
    ldap_object = LdapObject(
        dn="CN=Nick Janssen,OU=Users,OU=Magenta,DC=ad,DC=addev",
        postalAddress="foo",
        **{cpr_field: "123"},
    )

    ldap_connection.modify.side_effect = LDAPInvalidValueError("Invalid value")

    with capture_logs() as cap_logs:
        await asyncio.gather(
            dataloader.modify_ldap_object(ldap_object, "user"),
        )

        warnings = [w for w in cap_logs if w["log_level"] == "warning"]
        assert re.match(
            ".*Invalid value",
            str(warnings[-1]["event"]),
        )


async def test_modify_ldap_object_but_export_equals_false(
    dataloader: DataLoader, converter: MagicMock
):
    converter._export_to_ldap_.return_value = False
    ldap_object = LdapObject(
        dn="CN=Nick Janssen,OU=Users,OU=Magenta,DC=ad,DC=addev",
        postalAddress="foo",
    )

    with capture_logs() as cap_logs:
        await asyncio.gather(
            dataloader.modify_ldap_object(ldap_object, ""),
        )

        messages = [w for w in cap_logs if w["log_level"] == "info"]
        assert re.match(
            ".*_export_to_ldap_ == False",
            str(messages[-1]["event"]),
        )


async def test_load_mo_employee(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
) -> None:
    cpr_no = "1407711900"
    uuid = uuid4()

    legacy_graphql_session.execute.return_value = {
        "employees": {
            "objects": [
                {
                    "objects": [
                        {"cpr_no": cpr_no, "uuid": uuid, "validity": {"to": None}}
                    ]
                },
            ]
        }
    }

    expected_result = [Employee(**{"cpr_no": cpr_no, "uuid": uuid})]

    output = await asyncio.gather(
        dataloader.load_mo_employee(uuid),
    )

    assert output == expected_result


async def test_upload_mo_employee(
    legacy_model_client: AsyncMock, dataloader: DataLoader
) -> None:
    """Test that test_upload_mo_employee works as expected."""

    return_values = ["1", None, "3"]
    input_values = [1, 2, 3]
    for input_value, return_value in zip(input_values, return_values):
        legacy_model_client.upload.return_value = return_value

        result = await asyncio.gather(
            dataloader.upload_mo_objects([input_value]),
        )
        assert result[0] == return_value
        legacy_model_client.upload.assert_called_with([input_value])


async def test_make_overview_entry(dataloader: DataLoader):
    attributes = ["attr1", "attr2", "unknownattr"]
    superiors = ["sup1", "sup2"]
    entry = dataloader.make_overview_entry(attributes, superiors)

    assert list(entry["attributes"].keys()) == ["attr1", "attr2"]
    assert entry["superiors"] == superiors

    assert entry["attributes"]["attr1"]["single_value"] is False
    assert entry["attributes"]["attr2"]["single_value"] is True

    assert entry["attributes"]["attr1"]["field_type"] == "Boolean"
    assert entry["attributes"]["attr2"]["field_type"] == "Integer"


async def test_get_overview(dataloader: DataLoader):
    schema_mock = MagicMock()
    schema_mock.object_classes = {"object1": "foo"}

    with patch(
        "mo_ldap_import_export.dataloaders.get_ldap_schema",
        return_value=schema_mock,
    ), patch(
        "mo_ldap_import_export.dataloaders.get_ldap_attributes",
        return_value=["attr1", "attr2"],
    ), patch(
        "mo_ldap_import_export.dataloaders.get_ldap_superiors",
        return_value=["sup1", "sup2"],
    ):
        output = dataloader.load_ldap_overview()

    assert list(output["object1"]["attributes"].keys()) == ["attr1", "attr2"]
    assert output["object1"]["superiors"] == ["sup1", "sup2"]
    assert output["object1"]["attributes"]["attr1"]["single_value"] is False
    assert output["object1"]["attributes"]["attr2"]["single_value"] is True

    assert output["object1"]["attributes"]["attr1"]["field_type"] == "Boolean"
    assert output["object1"]["attributes"]["attr2"]["field_type"] == "Integer"


async def test_get_populated_overview(dataloader: DataLoader):
    overview = {
        "user": {"attributes": ["attr1", "attr2"], "superiors": ["sup1", "sup2"]}
    }

    responses = [
        {
            "attributes": {
                "attr1": "foo",  # We expect this attribute in the output
                "attr2": None,  # But not this one
                "objectClass": ["top", "person", "user"],
            }
        },
        {
            "attributes": {
                "attr1": "foo",
                "attr2": "bar",  # We still do not expect this one; wrong object class
                "objectClass": ["top", "person", "user", "computer"],
            }
        },
    ]

    with patch(
        "mo_ldap_import_export.dataloaders.DataLoader.load_ldap_overview",
        return_value=overview,
    ), patch(
        "mo_ldap_import_export.dataloaders.paged_search",
        return_value=responses,
    ):
        output = dataloader.load_ldap_populated_overview()

    assert sorted(list(output["user"]["attributes"].keys())) == sorted(
        ["attr1", "objectClass"]
    )
    assert output["user"]["superiors"] == ["sup1", "sup2"]
    assert output["user"]["attributes"]["attr1"]["single_value"] is False


async def test_load_mo_address_types(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
) -> None:
    uuid = uuid4()
    name = "Email"

    legacy_graphql_session.execute.return_value = {
        "facets": {
            "objects": [
                {"current": {"classes": [{"uuid": uuid, "name": name}]}},
            ]
        }
    }

    assert (await dataloader.load_mo_employee_address_types())[uuid]["name"] == name
    assert (await dataloader.load_mo_org_unit_address_types())[uuid]["name"] == name


async def test_load_mo_primary_types(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
) -> None:
    uuid = uuid4()
    value_key = "primary"

    legacy_graphql_session.execute.return_value = {
        "facets": {
            "objects": [
                {"current": {"classes": [{"uuid": uuid, "value_key": value_key}]}},
            ]
        }
    }

    output = await dataloader.load_mo_primary_types()
    assert output[uuid]["value_key"] == value_key


async def test_load_mo_job_functions(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
) -> None:
    uuid = uuid4()
    name = "Manager"

    legacy_graphql_session.execute.return_value = {
        "facets": {
            "objects": [
                {"current": {"classes": [{"uuid": uuid, "name": name}]}},
            ]
        }
    }

    output = await dataloader.load_mo_job_functions()
    assert output[uuid]["name"] == name


async def test_load_mo_visibility(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
) -> None:
    uuid = uuid4()
    name = "Hemmelig"

    legacy_graphql_session.execute.return_value = {
        "facets": {
            "objects": [
                {"current": {"classes": [{"uuid": uuid, "name": name}]}},
            ]
        }
    }

    output = await dataloader.load_mo_visibility()
    assert output[uuid]["name"] == name


async def test_load_mo_engagement_types(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
) -> None:
    uuid = uuid4()
    name = "Ansat"

    legacy_graphql_session.execute.return_value = {
        "facets": {
            "objects": [
                {"current": {"classes": [{"uuid": uuid, "name": name}]}},
            ]
        }
    }

    output = await dataloader.load_mo_engagement_types()
    assert output[uuid]["name"] == name


async def test_load_mo_org_unit_types(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
) -> None:
    uuid = uuid4()
    name = "Direktørområde"

    legacy_graphql_session.execute.return_value = {
        "facets": {
            "objects": [
                {"current": {"classes": [{"uuid": uuid, "name": name}]}},
            ]
        }
    }

    output = await dataloader.load_mo_org_unit_types()
    assert output[uuid]["name"] == name


async def test_load_mo_org_unit_levels(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
) -> None:
    uuid = uuid4()
    name = "N1"

    legacy_graphql_session.execute.return_value = {
        "facets": {
            "objects": [
                {"current": {"classes": [{"uuid": uuid, "name": name}]}},
            ]
        }
    }

    output = await dataloader.load_mo_org_unit_levels()
    assert output[uuid]["name"] == name


async def test_load_mo_address_no_valid_addresses(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
) -> None:
    uuid = uuid4()

    legacy_graphql_session.execute.return_value = {"addresses": {"objects": []}}

    with pytest.raises(NoObjectsReturnedException):
        await asyncio.gather(dataloader.load_mo_address(uuid))


async def test_load_mo_address(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
) -> None:
    uuid = uuid4()

    address_dict: dict = {
        "value": "foo@bar.dk",
        "uuid": uuid,
        "address_type": {"uuid": uuid},
        "validity": {"from": "2021-01-01 01:00", "to": None},
        "person": {"uuid": uuid},
        "org_unit": {"uuid": uuid},
        "visibility": {"uuid": uuid},
        "engagement": {"uuid": uuid},
    }

    # Note that 'Address' requires 'person' to be a dict
    expected_result = Address(**address_dict.copy())

    # While graphQL returns it as a list with length 1
    address_dict["person"] = [{"cpr_no": "0101012002"}]
    address_dict["address_type"]["user_key"] = "address"
    address_dict["value2"] = None
    address_dict["visibility_uuid"] = uuid
    address_dict["employee_uuid"] = uuid
    address_dict["org_unit_uuid"] = uuid
    address_dict["engagement_uuid"] = uuid

    legacy_graphql_session.execute.return_value = {
        "addresses": {
            "objects": [
                {"objects": [address_dict]},
            ]
        }
    }

    output = await asyncio.gather(
        dataloader.load_mo_address(uuid),
    )

    assert output[0] == expected_result


def test_load_ldap_object(dataloader: DataLoader):
    make_ldap_object = MagicMock()
    with patch(
        "mo_ldap_import_export.dataloaders.single_object_search",
        return_value="foo",
    ), patch(
        "mo_ldap_import_export.dataloaders.make_ldap_object",
        new_callable=make_ldap_object,
    ):
        dn = "CN=Nikki Minaj"
        output = dataloader.load_ldap_object(dn, ["foo", "bar"])
        assert output.called_once_with("foo", dataloader.context)


def test_cleanup_attributes_in_ldap(dataloader: DataLoader):
    dataloader.single_value = {"value": False}

    dataloader.shared_attribute = MagicMock()  # type: ignore
    dataloader.shared_attribute.return_value = False

    ldap_objects = [
        # LdapObject(dn="foo", value="New address"),
        LdapObject(dn="CN=foo", value="Old address"),
    ]

    with patch(
        "mo_ldap_import_export.dataloaders.DataLoader.load_ldap_object",
        return_value=LdapObject(dn="foo", value=["New address", "Old address"]),
    ):
        dataloader.cleanup_attributes_in_ldap(ldap_objects)

        changes = {"value": [("MODIFY_DELETE", "Old address")]}
        assert dataloader.ldap_connection.modify.called_once_with("foo", changes)

    with capture_logs() as cap_logs:
        ldap_objects = [LdapObject(dn="foo")]
        dataloader.cleanup_attributes_in_ldap(ldap_objects)

        infos = [w for w in cap_logs if w["log_level"] == "info"]
        assert re.match(
            ".*No cleanable attributes",
            infos[-1]["event"],
        )


async def test_load_mo_employee_addresses(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    address1_uuid = uuid4()
    address2_uuid = uuid4()

    legacy_graphql_session.execute.return_value = {
        "employees": {
            "objects": [
                {
                    "objects": [
                        {
                            "addresses": [
                                {"uuid": address1_uuid},
                                {"uuid": address2_uuid},
                            ]
                        }
                    ]
                },
            ]
        }
    }

    employee_uuid = uuid4()
    address_type_uuid = uuid4()

    load_mo_address = AsyncMock()
    dataloader.load_mo_address = load_mo_address  # type: ignore

    await asyncio.gather(
        dataloader.load_mo_employee_addresses(employee_uuid, address_type_uuid),
    )

    load_mo_address.assert_any_call(address1_uuid)
    load_mo_address.assert_any_call(address2_uuid)


async def test_load_mo_employee_addresses_not_found(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    legacy_graphql_session.execute.return_value = {"employees": {"objects": []}}

    with pytest.raises(NoObjectsReturnedException):
        await asyncio.gather(
            dataloader.load_mo_employee_addresses(uuid4(), uuid4()),
        )


async def test_find_mo_employee_uuid(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    uuid = uuid4()
    objectGUID = uuid4()
    dataloader.user_context["cpr_field"] = "employeeID"
    with patch(
        "mo_ldap_import_export.dataloaders.DataLoader.load_ldap_object",
        return_value=LdapObject(
            dn="CN=foo", employeeID="0101011221", objectGUID=str(objectGUID)
        ),
    ):
        return_value: dict = {
            "employees": {
                "objects": [
                    {"uuid": uuid},
                ]
            },
            "itusers": {"objects": []},
        }

        legacy_graphql_session.execute.return_value = return_value

        output = await asyncio.gather(
            dataloader.find_mo_employee_uuid("CN=foo"),
        )
        assert output[0] == uuid

    with patch(
        "mo_ldap_import_export.dataloaders.DataLoader.load_ldap_object",
        return_value=LdapObject(
            dn="CN=foo", employeeID="Ja", objectGUID=str(objectGUID)
        ),
    ):
        return_value = {
            "itusers": {
                "objects": [
                    {"objects": [{"employee_uuid": uuid}]},
                ]
            }
        }

        legacy_graphql_session.execute.return_value = return_value

        output = await asyncio.gather(dataloader.find_mo_employee_uuid("CN=foo"))
        assert output[0] == uuid


async def test_find_mo_employee_uuid_not_found(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    with patch(
        "mo_ldap_import_export.dataloaders.DataLoader.load_ldap_object",
        return_value=LdapObject(
            dn="CN=foo", employeeID="0101011221", objectGUID=str(uuid4())
        ),
    ):
        legacy_graphql_session.execute.return_value = {
            "employees": {"objects": []},
            "itusers": {"objects": []},
        }

        output = await asyncio.gather(dataloader.find_mo_employee_uuid("CN=foo"))

        assert output[0] is None


async def test_find_mo_employee_uuid_multiple_matches(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    with patch(
        "mo_ldap_import_export.dataloaders.DataLoader.load_ldap_object",
        return_value=LdapObject(
            dn="CN=foo", employeeID="0101011221", objectGUID=str(uuid4())
        ),
    ):
        legacy_graphql_session.execute.return_value = {
            "employees": {"objects": [{"uuid": uuid4()}, {"uuid": uuid4()}]},
            "itusers": {"objects": []},
        }

        with pytest.raises(MultipleObjectsReturnedException):
            await asyncio.gather(dataloader.find_mo_employee_uuid("CN=foo"))


async def test_load_mo_employee_not_found(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    legacy_graphql_session.execute.return_value = {"employees": {"objects": []}}

    uuid = uuid4()

    with pytest.raises(NoObjectsReturnedException):
        await asyncio.gather(
            dataloader.load_mo_employee(uuid),
        )


async def test_load_mo_address_types_not_found(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    legacy_graphql_session.execute.return_value = {"facets": {"objects": []}}

    assert await dataloader.load_mo_employee_address_types() == {}
    assert await dataloader.load_mo_org_unit_address_types() == {}


async def test_load_mo_it_systems(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    uuid1 = uuid4()
    uuid2 = uuid4()

    return_value = {
        "itsystems": {
            "objects": [
                {"current": {"user_key": "AD", "uuid": uuid1}},
                {"current": {"user_key": "Office365", "uuid": uuid2}},
            ]
        }
    }

    legacy_graphql_session.execute.return_value = return_value

    output = await dataloader.load_mo_it_systems()
    assert output[uuid1]["user_key"] == "AD"
    assert output[uuid2]["user_key"] == "Office365"


async def test_load_mo_org_units(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    uuid1 = str(uuid4())
    uuid2 = str(uuid4())

    return_value = {
        "org_units": {
            "objects": [
                {"objects": [{"name": "Magenta Aps", "uuid": uuid1}]},
                {
                    "objects": [
                        {
                            "name": "Magenta Aarhus",
                            "uuid": uuid2,
                            "parent_uuid": uuid1,
                        }
                    ]
                },
            ]
        }
    }

    legacy_graphql_session.execute.return_value = return_value

    output = await dataloader.load_mo_org_units()
    assert output[uuid1]["name"] == "Magenta Aps"
    assert output[uuid2]["name"] == "Magenta Aarhus"
    assert output[uuid2]["parent_uuid"] == uuid1


async def test_load_mo_org_units_empty_response(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    return_value: dict = {"org_units": {"objects": []}}

    legacy_graphql_session.execute.return_value = return_value

    output = await dataloader.load_mo_org_units()
    assert output == {}


async def test_load_mo_it_systems_not_found(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    return_value: dict = {"itsystems": {"objects": []}}
    legacy_graphql_session.execute.return_value = return_value

    output = await dataloader.load_mo_it_systems()
    assert output == {}


async def test_load_mo_it_user(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    uuid1 = uuid4()
    uuid2 = uuid4()
    return_value = {
        "itusers": {
            "objects": [
                {
                    "objects": [
                        {
                            "user_key": "foo",
                            "validity": {"from": "2021-01-01", "to": None},
                            "employee_uuid": uuid1,
                            "itsystem_uuid": uuid2,
                            "engagement_uuid": uuid1,
                        }
                    ]
                }
            ]
        }
    }

    legacy_graphql_session.execute.return_value = return_value

    output = await asyncio.gather(
        dataloader.load_mo_it_user(uuid4()),
    )
    assert output[0].user_key == "foo"
    assert output[0].itsystem.uuid == uuid2
    assert output[0].person.uuid == uuid1  # type: ignore
    assert output[0].engagement.uuid == uuid1  # type: ignore
    assert output[0].validity.from_date.strftime("%Y-%m-%d") == "2021-01-01"
    assert len(output) == 1


async def test_load_mo_engagement(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    return_value = {
        "engagements": {
            "objects": [
                {
                    "objects": [
                        {
                            "user_key": "foo",
                            "validity": {"from": "2021-01-01", "to": None},
                            "extension_1": "extra info",
                            "extension_2": "more extra info",
                            "extension_3": None,
                            "extension_4": None,
                            "extension_5": None,
                            "extension_6": None,
                            "extension_7": None,
                            "extension_8": None,
                            "extension_9": None,
                            "extension_10": None,
                            "leave_uuid": uuid4(),
                            "primary_uuid": uuid4(),
                            "job_function_uuid": uuid4(),
                            "org_unit_uuid": uuid4(),
                            "engagement_type_uuid": uuid4(),
                            "employee_uuid": uuid4(),
                        }
                    ]
                }
            ]
        }
    }

    legacy_graphql_session.execute.return_value = return_value

    output = await asyncio.gather(
        dataloader.load_mo_engagement(uuid4()),
    )
    assert output[0].user_key == "foo"
    assert output[0].validity.from_date.strftime("%Y-%m-%d") == "2021-01-01"
    assert output[0].extension_1 == "extra info"
    assert output[0].extension_2 == "more extra info"
    assert len(output) == 1


async def test_load_mo_it_user_not_found(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    return_value: dict = {"itusers": {"objects": []}}

    legacy_graphql_session.execute.return_value = return_value

    with pytest.raises(NoObjectsReturnedException):
        await asyncio.gather(
            dataloader.load_mo_it_user(uuid4()),
        )


async def test_load_mo_employee_it_users(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    uuid1 = uuid4()
    uuid2 = uuid4()
    employee_uuid = uuid4()
    it_system_uuid = uuid4()

    return_value = {
        "employees": {
            "objects": [
                {
                    "objects": [
                        {
                            "itusers": [
                                {
                                    "uuid": uuid1,
                                    "itsystem_uuid": str(it_system_uuid),
                                },
                                {
                                    "uuid": uuid2,
                                    "itsystem_uuid": str(uuid4()),
                                },
                            ]
                        }
                    ]
                }
            ]
        }
    }

    legacy_graphql_session.execute.return_value = return_value

    load_mo_it_user = AsyncMock()
    dataloader.load_mo_it_user = load_mo_it_user  # type: ignore

    await asyncio.gather(
        dataloader.load_mo_employee_it_users(employee_uuid, it_system_uuid),
    )

    load_mo_it_user.assert_called_once_with(uuid1)


async def test_load_mo_employees_in_org_unit(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    employee_uuid1 = uuid4()
    employee_uuid2 = uuid4()
    return_value = {
        "org_units": {
            "objects": [
                {
                    "objects": [
                        {
                            "engagements": [
                                {
                                    "employee_uuid": employee_uuid1,
                                },
                                {
                                    "employee_uuid": employee_uuid2,
                                },
                            ]
                        }
                    ]
                }
            ]
        }
    }

    legacy_graphql_session.execute.return_value = return_value

    load_mo_employee = AsyncMock()
    dataloader.load_mo_employee = load_mo_employee  # type: ignore

    await asyncio.gather(
        dataloader.load_mo_employees_in_org_unit(uuid4()),
    )

    load_mo_employee.assert_any_call(employee_uuid1)
    load_mo_employee.assert_any_call(employee_uuid2)


async def test_load_mo_org_unit_addresses(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    address_uuid1 = uuid4()
    address_uuid2 = uuid4()
    return_value = {
        "org_units": {
            "objects": [
                {
                    "objects": [
                        {
                            "addresses": [
                                {
                                    "uuid": address_uuid1,
                                },
                                {
                                    "uuid": address_uuid2,
                                },
                            ]
                        }
                    ]
                }
            ]
        }
    }

    legacy_graphql_session.execute.return_value = return_value

    load_mo_address = AsyncMock()
    dataloader.load_mo_address = load_mo_address  # type: ignore

    await asyncio.gather(
        dataloader.load_mo_org_unit_addresses(uuid4(), uuid4()),
    )

    load_mo_address.assert_any_call(address_uuid1)
    load_mo_address.assert_any_call(address_uuid2)


async def test_load_mo_employee_engagements(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    uuid1 = uuid4()
    employee_uuid = uuid4()

    return_value = {
        "engagements": {
            "objects": [
                {
                    "uuid": uuid1,
                },
            ]
        }
    }

    legacy_graphql_session.execute.return_value = return_value

    load_mo_engagement = AsyncMock()
    dataloader.load_mo_engagement = load_mo_engagement  # type: ignore

    await asyncio.gather(
        dataloader.load_mo_employee_engagements(employee_uuid),
    )

    load_mo_engagement.assert_called_once_with(uuid1)


async def test_load_mo_employee_it_users_not_found(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    return_value: dict = {"employees": {"objects": []}}

    legacy_graphql_session.execute.return_value = return_value

    with pytest.raises(NoObjectsReturnedException):
        await asyncio.gather(
            dataloader.load_mo_employee_it_users(uuid4(), uuid4()),
        )


async def test_is_primary(dataloader: DataLoader, legacy_graphql_session: AsyncMock):
    return_value: dict = {
        "engagements": {"objects": [{"objects": [{"is_primary": True}]}]}
    }

    legacy_graphql_session.execute.return_value = return_value

    primary = await asyncio.gather(dataloader.is_primary(uuid4()))
    assert primary == [True]


async def test_query_mo(dataloader: DataLoader, legacy_graphql_session: AsyncMock):
    expected_output: dict = {"objects": {"objects": []}}
    legacy_graphql_session.execute.return_value = expected_output

    query = gql(
        """
        query TestQuery {
          employees {
            uuid
          }
        }
        """
    )

    output = await asyncio.gather(dataloader.query_mo(query, raise_if_empty=False))
    assert output == [expected_output]

    with pytest.raises(NoObjectsReturnedException):
        await asyncio.gather(dataloader.query_mo(query, raise_if_empty=True))


async def test_query_mo_all_objects(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    query = gql(
        """
        query TestQuery {
          employees (uuid:"uuid") {
            uuid
          }
        }
        """
    )

    expected_output: list = [
        {"objects": {"objects": []}},
        {"objects": {"objects": ["item1", "item2"]}},
    ]
    legacy_graphql_session.execute.side_effect = expected_output

    output = await asyncio.gather(
        dataloader.query_past_future_mo(query, current_objects_only=False)
    )
    assert output == [expected_output[1]]

    query1 = print_ast(legacy_graphql_session.execute.call_args_list[0].args[0])
    query2 = print_ast(legacy_graphql_session.execute.call_args_list[1].args[0])

    # The first query attempts to request current objects only
    assert "from_date" not in query1
    assert "to_date" not in query1

    # If that fails, all objects are requested
    assert "from_date" in query2
    assert "to_date" in query2


async def test_load_all_mo_objects(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    return_values: list = [
        {"employees": {"objects": [{"objects": [{"uuid": str(uuid4())}]}]}},
        {"org_units": {"objects": [{"objects": [{"uuid": str(uuid4())}]}]}},
        {
            "addresses": {
                "objects": [
                    {
                        "objects": [
                            {
                                "uuid": str(uuid4()),
                                "employee_uuid": str(uuid4()),
                                "org_unit_uuid": None,
                            },
                        ]
                    },
                    {
                        "objects": [
                            {
                                "uuid": str(uuid4()),
                                "employee_uuid": None,
                                "org_unit_uuid": str(uuid4()),
                            },
                        ]
                    },
                ]
            }
        },
        {
            "itusers": {
                "objects": [
                    {
                        "objects": [
                            {
                                "uuid": str(uuid4()),
                                "employee_uuid": str(uuid4()),
                                "org_unit_uuid": None,
                            }
                        ]
                    }
                ]
            }
        },
        {
            "engagements": {
                "objects": [
                    {
                        "objects": [
                            {
                                "uuid": str(uuid4()),
                                "employee_uuid": str(uuid4()),
                                "org_unit_uuid": str(uuid4()),
                            }
                        ]
                    }
                ]
            },
        },
    ]

    dataloader.query_mo_paged = AsyncMock()  # type: ignore
    dataloader.query_mo_paged.side_effect = return_values
    all_objects = await dataloader.load_all_mo_objects()

    uuid = return_values[0]["employees"]["objects"][0]["objects"][0]["uuid"]
    parent_uuid = uuid
    assert all_objects[0]["uuid"] == uuid
    assert all_objects[0]["object_type"] == "person"
    assert all_objects[0]["service_type"] == "employee"
    assert all_objects[0]["parent_uuid"] == UUID(parent_uuid)
    assert all_objects[0]["payload"] == UUID(uuid)

    uuid = return_values[1]["org_units"]["objects"][0]["objects"][0]["uuid"]
    parent_uuid = uuid
    assert all_objects[1]["uuid"] == uuid
    assert all_objects[1]["object_type"] == "org_unit"
    assert all_objects[1]["service_type"] == "org_unit"
    assert all_objects[1]["parent_uuid"] == UUID(parent_uuid)
    assert all_objects[1]["payload"] == UUID(uuid)

    uuid = return_values[2]["addresses"]["objects"][0]["objects"][0]["uuid"]
    parent_uuid = return_values[2]["addresses"]["objects"][0]["objects"][0][
        "employee_uuid"
    ]
    assert all_objects[2]["uuid"] == uuid
    assert all_objects[2]["object_type"] == "address"
    assert all_objects[2]["service_type"] == "employee"
    assert all_objects[2]["parent_uuid"] == UUID(parent_uuid)
    assert all_objects[2]["payload"] == UUID(uuid)

    uuid = return_values[2]["addresses"]["objects"][1]["objects"][0]["uuid"]
    parent_uuid = return_values[2]["addresses"]["objects"][1]["objects"][0][
        "org_unit_uuid"
    ]
    assert all_objects[3]["uuid"] == uuid
    assert all_objects[3]["object_type"] == "address"
    assert all_objects[3]["service_type"] == "org_unit"
    assert all_objects[3]["parent_uuid"] == UUID(parent_uuid)
    assert all_objects[3]["payload"] == UUID(uuid)

    uuid = return_values[3]["itusers"]["objects"][0]["objects"][0]["uuid"]
    parent_uuid = return_values[3]["itusers"]["objects"][0]["objects"][0][
        "employee_uuid"
    ]
    assert all_objects[4]["uuid"] == uuid
    assert all_objects[4]["object_type"] == "ituser"
    assert all_objects[4]["service_type"] == "employee"
    assert all_objects[4]["parent_uuid"] == UUID(parent_uuid)
    assert all_objects[4]["payload"] == UUID(uuid)

    uuid = return_values[4]["engagements"]["objects"][0]["objects"][0]["uuid"]
    parent_uuid = return_values[4]["engagements"]["objects"][0]["objects"][0][
        "employee_uuid"
    ]
    assert all_objects[5]["uuid"] == uuid
    assert all_objects[5]["object_type"] == "engagement"
    assert all_objects[5]["service_type"] == "employee"
    assert all_objects[5]["parent_uuid"] == UUID(parent_uuid)
    assert all_objects[5]["payload"] == UUID(uuid)

    assert len(all_objects) == 6


async def test_load_all_mo_objects_add_validity(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    query_mo = AsyncMock()
    query_mo.return_value = {}
    dataloader.query_mo = query_mo  # type: ignore

    await dataloader.load_all_mo_objects(add_validity=True, uuid=str(uuid4()))
    query = print_ast(query_mo.call_args[0][0])
    assert "validity" in str(query)

    query_mo.reset_mock()

    await dataloader.load_all_mo_objects(add_validity=False, uuid=str(uuid4()))
    query = print_ast(query_mo.call_args[0][0])
    assert "validity" not in str(query)


async def test_load_all_mo_objects_current_objects_only(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    query_mo = AsyncMock()
    query_mo.return_value = {}
    dataloader.query_mo = query_mo  # type: ignore

    await dataloader.load_all_mo_objects(current_objects_only=True, uuid=str(uuid4()))
    query = print_ast(query_mo.call_args[0][0])
    assert "to_date: null" not in str(query)
    assert "from_date: null" not in str(query)

    query_mo.reset_mock()

    await dataloader.load_all_mo_objects(current_objects_only=False, uuid=str(uuid4()))
    query = print_ast(query_mo.call_args[0][0])
    assert "to_date: null" in str(query)
    assert "from_date: null" in str(query)


async def test_load_all_mo_objects_specify_uuid(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    employee_uuid = str(uuid4())
    return_values: list = [
        {"employees": {"objects": [{"objects": [{"uuid": employee_uuid}]}]}},
        {"org_units": {"objects": []}},
        {"addresses": {"objects": []}},
        {"engagements": {"objects": []}},
        {"itusers": {"objects": []}},
    ]

    legacy_graphql_session.execute.side_effect = return_values

    output = await dataloader.load_all_mo_objects(uuid=employee_uuid)
    assert output[0]["uuid"] == employee_uuid
    assert len(output) == 1


async def test_load_all_mo_objects_specify_uuid_multiple_results(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    uuid = str(uuid4())
    return_values: list = [
        {"employees": {"objects": [{"objects": [{"uuid": uuid}]}]}},
        {"org_units": {"objects": [{"objects": [{"uuid": uuid}]}]}},
        {"addresses": {"objects": []}},
        {"engagements": {"objects": []}},
        {"itusers": {"objects": []}},
    ]

    dataloader.query_mo = AsyncMock()  # type: ignore
    dataloader.query_mo.side_effect = return_values

    with pytest.raises(MultipleObjectsReturnedException):
        await dataloader.load_all_mo_objects(uuid=uuid)


async def test_load_all_mo_objects_invalid_query(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    # Return a single it-user, which belongs neither to an employee nor org-unit
    return_value: dict = {
        "itusers": {
            "objects": [
                {
                    "objects": [
                        {"uuid": uuid4(), "employee_uuid": None, "org_unit_uuid": None}
                    ]
                }
            ]
        },
    }

    dataloader.query_mo_paged = AsyncMock()  # type: ignore
    dataloader.query_mo_paged.return_value = return_value

    with pytest.raises(InvalidQueryResponse):
        await dataloader.load_all_mo_objects()


async def test_load_all_mo_objects_TransportQueryError(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    employee_uuid = str(uuid4())
    org_unit_uuid = str(uuid4())
    return_values = [
        {"employees": {"objects": [{"objects": [{"uuid": employee_uuid}]}]}},
        {"org_units": {"objects": [{"objects": [{"uuid": org_unit_uuid}]}]}},
        TransportQueryError("foo"),
        TransportQueryError("foo"),
        TransportQueryError("foo"),
    ]

    dataloader.query_mo_paged = AsyncMock()  # type: ignore
    dataloader.query_mo_paged.side_effect = return_values

    with capture_logs() as cap_logs:
        output = await dataloader.load_all_mo_objects()
        warnings = [w for w in cap_logs if w["log_level"] == "warning"]
        assert len(warnings) == 0

        assert output[0]["uuid"] == employee_uuid
        assert output[1]["uuid"] == org_unit_uuid
        assert len(output) == 2


async def test_load_all_mo_objects_only_TransportQueryErrors(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    return_values = [
        TransportQueryError("foo"),
        TransportQueryError("foo"),
        TransportQueryError("foo"),
        TransportQueryError("foo"),
        TransportQueryError("foo"),
    ]

    dataloader.query_mo_paged = AsyncMock()  # type: ignore
    dataloader.query_mo_paged.side_effect = return_values

    with capture_logs() as cap_logs:
        await dataloader.load_all_mo_objects()
        warnings = [w for w in cap_logs if w["log_level"] == "warning"]
        assert len(warnings) == 5


async def test_load_all_mo_objects_invalid_object_type_to_try(
    dataloader: DataLoader, legacy_graphql_session: AsyncMock
):
    with pytest.raises(KeyError):
        await asyncio.gather(
            dataloader.load_all_mo_objects(
                object_types_to_try=("non_existing_object_type",)
            )
        )


async def test_shared_attribute(dataloader: DataLoader):
    converter = MagicMock()
    converter.mapping = {
        "mo_to_ldap": {
            "Employee": {"cpr_no": None, "name": None},
            "Address": {"cpr_no": None, "value": None},
        }
    }
    dataloader.user_context["converter"] = converter

    assert dataloader.shared_attribute("cpr_no") is True
    assert dataloader.shared_attribute("name") is False
    assert dataloader.shared_attribute("value") is False

    with pytest.raises(AttributeNotFound):
        dataloader.shared_attribute("non_existing_attribute")


async def test_load_mo_object(dataloader: DataLoader):
    with patch(
        "mo_ldap_import_export.dataloaders.DataLoader.load_all_mo_objects",
        return_value=["obj1"],
    ):
        result = await asyncio.gather(dataloader.load_mo_object("uuid", "person"))
        assert result[0] == "obj1"

    with patch(
        "mo_ldap_import_export.dataloaders.DataLoader.load_all_mo_objects",
        return_value=[],
    ):
        with pytest.raises(NoObjectsReturnedException):
            await dataloader.load_mo_object("uuid", "person")

    # Role is not defined in self.object_type_dict
    # Hence we will not be able to find the object
    result = await dataloader.load_mo_object("uuid", "role")
    assert result is None


async def test_modify_ldap(
    dataloader: DataLoader,
    sync_tool: AsyncMock,
    ldap_connection: MagicMock,
):
    ldap_connection.result = {"description": "success"}
    dn = "CN=foo"
    changes: dict = {"parameter_to_modify": [("MODIFY_ADD", "value_to_modify")]}

    # Validate that the entry is not in the ignore dict
    assert len(sync_tool.dns_to_ignore[dn]) == 0

    # Modify the entry. Validate that it is added to the ignore dict
    dataloader.modify_ldap(dn, changes)
    assert len(sync_tool.dns_to_ignore[dn]) == 1

    # Modify the same entry again. Validate that we still only ignore once
    dataloader.modify_ldap(dn, changes)
    assert len(sync_tool.dns_to_ignore[dn]) == 1

    # Validate that any old entries get cleaned, and a new one gets added
    sync_tool.dns_to_ignore.ignore_dict[dn.lower()] = [
        datetime.datetime(1900, 1, 1),
        datetime.datetime(1901, 1, 1),
    ]
    assert len(sync_tool.dns_to_ignore[dn]) == 2
    dataloader.modify_ldap(dn, changes)
    assert len(sync_tool.dns_to_ignore[dn]) == 1
    assert sync_tool.dns_to_ignore[dn][0] > datetime.datetime(1950, 1, 1)

    # Validate that our checks work
    with pytest.raises(
        InvalidChangeDict, match="Exactly one attribute can be changed at a time"
    ):
        changes = {
            "parameter_to_modify": [("MODIFY_ADD", "value_to_modify")],
            "another_parameter_to_modify": [("MODIFY_ADD", "value_to_modify")],
        }
        dataloader.modify_ldap(dn, changes)

    # Validate that our checks work
    with pytest.raises(
        InvalidChangeDict, match="Exactly one change can be submitted at a time"
    ):
        changes = {
            "parameter_to_modify": [
                ("MODIFY_ADD", "value_to_modify"),
                ("MODIFY_ADD", "another_value_to_modify"),
            ],
        }
        dataloader.modify_ldap(dn, changes)

    # Validate that our checks work
    with pytest.raises(
        InvalidChangeDict, match="Exactly one value can be changed at a time"
    ):
        changes = {
            "parameter_to_modify": [
                (
                    "MODIFY_ADD",
                    [
                        "value_to_modify",
                        "another_value_to_modify",
                    ],
                )
            ],
        }
        dataloader.modify_ldap(dn, changes)

    # Validate that empty lists are allowed
    changes = {"parameter_to_modify": [("MODIFY_REPLACE", [])]}
    dataloader.modify_ldap(dn, changes)
    ldap_connection.compare.assert_called_with(dn, "parameter_to_modify", "")

    # Simulate case where a value exists
    ldap_connection.compare.return_value = True
    with capture_logs() as cap_logs:
        dataloader.modify_ldap(dn, changes)
        messages = [w for w in cap_logs if w["log_level"] == "info"]

        assert re.match(".*already exists.*", str(messages[-1]["event"]))

    # DELETE statments should still be executed, even if a value exists
    changes = {"parameter_to_modify": [("MODIFY_DELETE", "foo")]}
    response = dataloader.modify_ldap(dn, changes)
    assert response == {"description": "success"}


async def test_modify_ldap_ou_not_in_ous_to_write_to(
    dataloader: DataLoader,
    sync_tool: AsyncMock,
    ldap_connection: MagicMock,
):
    dataloader.ou_in_ous_to_write_to = MagicMock()  # type: ignore
    dataloader.ou_in_ous_to_write_to.return_value = False

    assert dataloader.modify_ldap("CN=foo", {}) is None  # type: ignore


async def test_get_ldap_it_system_uuid(dataloader: DataLoader, converter: MagicMock):
    uuid = uuid4()
    converter.get_it_system_uuid.return_value = uuid
    assert dataloader.get_ldap_it_system_uuid() == uuid

    converter.get_it_system_uuid.side_effect = UUIDNotFoundException("UUID Not found")
    assert dataloader.get_ldap_it_system_uuid() is None


async def test_find_or_make_mo_employee_dn(
    dataloader: DataLoader, username_generator: MagicMock
):
    uuid_1 = uuid4()
    uuid_2 = uuid4()

    it_system_uuid = uuid4()
    dataloader.get_ldap_it_system_uuid = MagicMock()  # type: ignore
    dataloader.load_mo_employee_it_users = AsyncMock()  # type: ignore
    dataloader.load_mo_employee = AsyncMock()  # type: ignore
    dataloader.load_ldap_cpr_object = AsyncMock()  # type: ignore
    dataloader.upload_mo_objects = AsyncMock()  # type: ignore
    dataloader.extract_unique_dns = MagicMock()  # type: ignore
    dataloader.get_ldap_unique_ldap_uuid = MagicMock()  # type: ignore

    # Case where there is an IT-system that contains the DN
    dataloader.load_mo_employee.return_value = Employee(cpr_no=None)
    dataloader.load_mo_employee_it_users.return_value = []
    dataloader.get_ldap_it_system_uuid.return_value = str(it_system_uuid)
    dataloader.extract_unique_dns.return_value = ["CN=foo,DC=bar"]
    dns = await dataloader.find_or_make_mo_employee_dn(uuid4())
    assert dns == ["CN=foo,DC=bar"]

    # Same as above, but the it-system contains an invalid value
    dataloader.extract_unique_dns.return_value = []
    username_generator.generate_dn.return_value = "CN=generated_dn_1,DC=DN"
    dataloader.get_ldap_unique_ldap_uuid.return_value = uuid_1
    dns = await dataloader.find_or_make_mo_employee_dn(uuid4())
    uploaded_uuid = dataloader.upload_mo_objects.await_args_list[0].args[0][0].user_key
    assert dns == ["CN=generated_dn_1,DC=DN"]
    assert uploaded_uuid == str(uuid_1)
    dataloader.upload_mo_objects.reset_mock()

    # Same as above, but there are multiple IT-users
    dataloader.extract_unique_dns.return_value = ["CN=foo,DC=bar", "CN=foo2,DC=bar"]
    dns = await dataloader.find_or_make_mo_employee_dn(uuid4())
    assert dns == ["CN=foo,DC=bar", "CN=foo2,DC=bar"]

    # Case where there is no IT-system that contains the DN, but the cpr lookup succeeds
    dataloader.load_mo_employee.return_value = Employee(cpr_no="0101911234")
    dataloader.extract_unique_dns.return_value = []
    dataloader.load_ldap_cpr_object.return_value = LdapObject(
        dn="CN=dn_already_in_ldap,DC=foo"
    )
    dns = await dataloader.find_or_make_mo_employee_dn(uuid4())
    assert dns == ["CN=dn_already_in_ldap,DC=foo"]

    # Same as above, but the cpr-lookup does not succeed
    dataloader.load_ldap_cpr_object.side_effect = NoObjectsReturnedException("foo")
    username_generator.generate_dn.return_value = "CN=generated_dn_2,DC=DN"
    dataloader.get_ldap_unique_ldap_uuid.return_value = uuid_2
    dns = await dataloader.find_or_make_mo_employee_dn(uuid4())
    uploaded_uuid = dataloader.upload_mo_objects.await_args_list[0].args[0][0].user_key
    assert dns == ["CN=generated_dn_2,DC=DN"]
    assert uploaded_uuid == str(uuid_2)
    dataloader.upload_mo_objects.reset_mock()

    # Same as above, but an it-system does not exist
    dataloader.get_ldap_it_system_uuid.return_value = None
    username_generator.generate_dn.return_value = "CN=generated_dn_3,DC=DN"
    dns = await dataloader.find_or_make_mo_employee_dn(uuid4())
    assert dns == ["CN=generated_dn_3,DC=DN"]
    dataloader.upload_mo_objects.assert_not_awaited()
    dataloader.upload_mo_objects.reset_mock()

    # Same as above, but the user also has no cpr number
    dataloader.load_mo_employee.return_value = Employee(cpr_no=None)
    with pytest.raises(DNNotFound):
        await dataloader.find_or_make_mo_employee_dn(uuid4())


def test_extract_unique_objectGUIDs(dataloader: DataLoader):
    ad_it_user_1 = ITUser.from_simplified_fields(
        str(uuid4()),
        uuid4(),
        datetime.datetime.today().strftime("%Y-%m-%d"),
        person_uuid=uuid4(),
    )
    ad_it_user_2 = ITUser.from_simplified_fields(
        str(uuid4()),
        uuid4(),
        datetime.datetime.today().strftime("%Y-%m-%d"),
        person_uuid=uuid4(),
    )
    ad_it_user_3 = ITUser.from_simplified_fields(
        "not_an_uuid",
        uuid4(),
        datetime.datetime.today().strftime("%Y-%m-%d"),
        person_uuid=uuid4(),
    )

    objectGUIDs = dataloader.extract_unique_ldap_uuids(
        [ad_it_user_1, ad_it_user_2, ad_it_user_3]
    )

    assert UUID(ad_it_user_1.user_key) in objectGUIDs
    assert UUID(ad_it_user_2.user_key) in objectGUIDs
    assert len(objectGUIDs) == 2


def test_extract_unique_dns(dataloader: DataLoader):
    dataloader.extract_unique_ldap_uuids = MagicMock()  # type: ignore
    dataloader.extract_unique_ldap_uuids.return_value = [uuid4(), uuid4()]

    dataloader.get_ldap_dn = MagicMock()  # type: ignore
    dataloader.get_ldap_dn.return_value = "CN=foo"

    dns = dataloader.extract_unique_dns([])

    assert len(dns) == 2
    assert dns[0] == "CN=foo"
    assert dns[1] == "CN=foo"


def test_get_ldap_dn(dataloader: DataLoader):
    with patch(
        "mo_ldap_import_export.dataloaders.single_object_search",
        return_value={"dn": "CN=foo"},
    ):
        assert dataloader.get_ldap_dn(uuid4()) == "CN=foo"


async def test_get_ldap_unique_ldap_uuid(dataloader: DataLoader):
    uuid = uuid4()
    dataloader.load_ldap_object = MagicMock()  # type: ignore
    dataloader.load_ldap_object.return_value = LdapObject(
        dn="foo", objectGUID=str(uuid)
    )

    assert await dataloader.get_ldap_unique_ldap_uuid("") == uuid


def test_load_ldap_attribute_values(dataloader: DataLoader):
    responses = [
        {"attributes": {"foo": 1}},
        {"attributes": {"foo": "2"}},
        {"attributes": {"foo": []}},
    ]
    with patch(
        "mo_ldap_import_export.dataloaders.paged_search",
        return_value=responses,
    ):
        values = dataloader.load_ldap_attribute_values("foo")
        assert "1" in values
        assert "2" in values
        assert "[]" in values
        assert len(values) == 3


async def test_create_mo_class(dataloader: DataLoader):
    uuid = uuid4()
    existing_class_uuid = uuid4()

    dataloader.query_mo = AsyncMock()  # type: ignore

    class_not_found_response: dict = {"classes": {"objects": []}}
    class_create_response: dict = {"class_create": {"uuid": str(uuid)}}
    class_exists_response = {
        "classes": {"objects": [{"uuid": str(existing_class_uuid)}]}
    }

    async def query_mo_mock(query, *args, **kwargs):
        query_str = print_ast(query)
        if "CreateClass" in query_str:
            await asyncio.sleep(0.1)
            return class_create_response
        else:
            return class_not_found_response

    async def query_mo_mock_class_exists(query, *args, **kwargs):
        query_str = print_ast(query)
        if "CreateClass" in query_str:
            return class_create_response
        else:
            return class_exists_response

    # Case1: The class does not exist yet
    dataloader.query_mo = query_mo_mock  # type: ignore
    assert await dataloader.create_mo_class("", "", uuid4()) == uuid

    # Case2: The class already exists
    dataloader.query_mo = query_mo_mock_class_exists  # type: ignore
    assert await dataloader.create_mo_class("", "", uuid4()) == existing_class_uuid

    # Case3: We call the function twice and the first one needs to wait for the second
    dataloader.query_mo = query_mo_mock  # type: ignore

    # Because of the lock, only one instance can run at the time.
    t1 = time.time()
    await asyncio.gather(
        dataloader.create_mo_class("n", "user_key", uuid4()),
        dataloader.create_mo_class("n", "user_key", uuid4()),
    )
    t2 = time.time()
    assert (t2 - t1) > 0.2  # each task takes 0.1 second


async def test_update_mo_class(dataloader: DataLoader):
    uuid = uuid4()

    dataloader.query_mo = AsyncMock()  # type: ignore
    dataloader.query_mo.return_value = {"class_update": {"uuid": str(uuid)}}

    assert await dataloader.update_mo_class("", "", uuid4(), uuid4()) == uuid


async def test_create_mo_job_function(dataloader: DataLoader):
    uuid1 = uuid4()
    uuid2 = uuid4()

    dataloader.load_mo_facet_uuid = AsyncMock()  # type: ignore
    dataloader.load_mo_facet_uuid.return_value = uuid1

    dataloader.create_mo_class = AsyncMock()  # type: ignore
    dataloader.create_mo_class.return_value = uuid2

    assert await dataloader.create_mo_job_function("foo") == uuid2
    assert await dataloader.create_mo_engagement_type("bar") == uuid2

    args = dataloader.create_mo_class.call_args_list[0].args

    assert args[0] == "foo"
    assert args[1] == "foo"
    assert args[2] == uuid1

    args = dataloader.create_mo_class.call_args_list[1].args

    assert args[0] == "bar"
    assert args[1] == "bar"
    assert args[2] == uuid1


async def test_load_mo_facet_uuid(dataloader: DataLoader):
    uuid = uuid4()
    dataloader.query_mo = AsyncMock()  # type: ignore
    dataloader.query_mo.return_value = {
        "facets": {"objects": [{"current": {"uuid": str(uuid)}}]}
    }

    assert await dataloader.load_mo_facet_uuid("") == uuid


async def test_load_mo_facet_uuid_multiple_facets(dataloader: DataLoader):
    dataloader.query_mo = AsyncMock()  # type: ignore
    dataloader.query_mo.return_value = {
        "facets": {
            "objects": [
                {"current": {"uuid": str(uuid4())}},
                {"current": {"uuid": str(uuid4())}},
            ]
        }
    }

    with pytest.raises(MultipleObjectsReturnedException):
        await dataloader.load_mo_facet_uuid("")


async def test_create_mo_it_system(dataloader: DataLoader):
    dataloader.query_mo = AsyncMock()  # type: ignore
    dataloader.query_mo.return_value = {"itsystem_create": {"uuid": str(uuid4())}}

    assert type(await dataloader.create_mo_it_system("foo", "bar")) == UUID


def test_add_ldap_object(dataloader: DataLoader):
    dataloader.add_ldap_object("CN=foo", attributes={"foo": 2})
    dataloader.ldap_connection.add.assert_called_once()

    dataloader.user_context["settings"] = MagicMock()  # type: ignore
    dataloader.user_context["settings"].add_objects_to_ldap = False

    with pytest.raises(NotEnabledException):
        dataloader.add_ldap_object("CN=foo")

    dataloader.ldap_connection.reset_mock()
    dataloader.user_context["settings"].add_objects_to_ldap = True
    dataloader.ou_in_ous_to_write_to = MagicMock()  # type: ignore
    dataloader.ou_in_ous_to_write_to.return_value = False

    dataloader.add_ldap_object("CN=foo")
    dataloader.ldap_connection.add.assert_not_called()


async def test_load_mo_employee_engagement_dicts(dataloader: DataLoader):
    dataloader.query_mo = AsyncMock()  # type: ignore
    engagement1 = {
        "uuid": uuid4(),
        "user_key": "foo",
        "org_unit_uuid": uuid4(),
        "job_function_uuid": uuid4(),
        "engagement_type_uuid": uuid4(),
    }
    engagement2 = {
        "uuid": uuid4(),
        "user_key": "foo",
        "org_unit_uuid": uuid4(),
        "job_function_uuid": uuid4(),
        "engagement_type_uuid": uuid4(),
    }
    dataloader.query_mo.return_value = {
        "engagements": {"objects": [{"current": engagement1}, {"current": engagement2}]}
    }

    result = await dataloader.load_mo_employee_engagement_dicts(uuid4(), "foo")

    assert engagement1 in result
    assert engagement2 in result

    dataloader.query_mo.side_effect = NoObjectsReturnedException("f")
    result = await dataloader.load_mo_employee_engagement_dicts(uuid4(), "foo")

    assert isinstance(result, list)
    assert len(result) == 0


def test_return_mo_employee_uuid_result(dataloader: DataLoader):
    uuid = uuid4()

    result: dict = {"employees": {"objects": []}, "itusers": {"objects": []}}
    assert dataloader._return_mo_employee_uuid_result(result) is None

    result = {"employees": {"objects": [{"uuid": uuid}]}, "itusers": {"objects": []}}
    assert dataloader._return_mo_employee_uuid_result(result) == uuid

    result = {"itusers": {"objects": [{"objects": [{"employee_uuid": uuid}]}]}}
    assert dataloader._return_mo_employee_uuid_result(result) == uuid

    result = {
        "itusers": {
            "objects": [
                {"objects": [{"employee_uuid": uuid}]},
                {"objects": [{"employee_uuid": uuid}]},
            ]
        }
    }
    assert dataloader._return_mo_employee_uuid_result(result) == uuid

    result = {
        "itusers": {
            "objects": [
                {"objects": [{"employee_uuid": uuid, "cpr_no": "010101-1234"}]},
                {"objects": [{"employee_uuid": uuid4(), "cpr_no": "010101-1234"}]},
            ]
        }
    }
    with pytest.raises(MultipleObjectsReturnedException, match="010101-xxxx"):
        dataloader._return_mo_employee_uuid_result(result)

    result = {
        "employees": {
            "objects": [
                {"uuid": uuid, "cpr_no": "010101-1234"},
                {"uuid": uuid4(), "cpr_no": "010101-1234"},
            ]
        },
        "itusers": {"objects": []},
    }
    with pytest.raises(MultipleObjectsReturnedException, match="010101-xxxx"):
        dataloader._return_mo_employee_uuid_result(result)


def test_ou_in_ous_to_write_to(dataloader: DataLoader):
    settings_mock = MagicMock()
    settings_mock.ldap_ous_to_write_to = ["OU=foo", "OU=mucki,OU=bar"]
    dataloader.user_context["settings"] = settings_mock

    assert dataloader.ou_in_ous_to_write_to("CN=Tobias,OU=foo,DC=k") is True
    assert dataloader.ou_in_ous_to_write_to("CN=Tobias,OU=bar,DC=k") is False
    assert dataloader.ou_in_ous_to_write_to("CN=Tobias,OU=mucki,OU=bar,DC=k") is True
    assert dataloader.ou_in_ous_to_write_to("CN=Tobias,DC=k") is False

    settings_mock.ldap_ous_to_write_to = [""]
    dataloader.user_context["settings"] = settings_mock

    assert dataloader.ou_in_ous_to_write_to("CN=Tobias,OU=foo,DC=k") is True
    assert dataloader.ou_in_ous_to_write_to("CN=Tobias,OU=bar,DC=k") is True
    assert dataloader.ou_in_ous_to_write_to("CN=Tobias,OU=mucki,OU=bar,DC=k") is True
    assert dataloader.ou_in_ous_to_write_to("CN=Tobias,DC=k") is True


async def test_load_all_current_it_users(dataloader: DataLoader):
    itsystem1_uuid = uuid4()
    itsystem2_uuid = uuid4()

    obj1 = {
        "itusers": {
            "objects": [
                {
                    "current": {
                        "itsystem_uuid": str(itsystem1_uuid),
                        "employee_uuid": str(uuid4()),
                        "user_key": "foo",
                    }
                }
            ]
        }
    }

    obj2 = {
        "itusers": {
            "objects": [
                {
                    "current": {
                        "itsystem_uuid": str(itsystem2_uuid),
                        "employee_uuid": str(uuid4()),
                        "user_key": "bar",
                    }
                }
            ]
        }
    }

    object_dicts = [obj1, obj2]

    dataloader.query_mo_paged = AsyncMock()  # type: ignore
    dataloader.query_mo_paged.side_effect = object_dicts

    output = await dataloader.load_all_current_it_users(itsystem1_uuid)

    assert len(output) == 1
    assert output[0]["itsystem_uuid"] == str(itsystem1_uuid)
    assert output[0]["user_key"] == "foo"

    output = await dataloader.load_all_current_it_users(itsystem2_uuid)

    assert len(output) == 1
    assert output[0]["itsystem_uuid"] == str(itsystem2_uuid)
    assert output[0]["user_key"] == "bar"


async def test_load_all_it_users(dataloader: DataLoader):
    itsystem1_uuid = uuid4()
    itsystem2_uuid = uuid4()

    result = {
        "itusers": {
            "objects": [
                {
                    "objects": [
                        {
                            "itsystem_uuid": str(itsystem1_uuid),
                            "employee_uuid": str(uuid4()),
                            "user_key": "mucki",
                        },
                        {
                            "itsystem_uuid": str(itsystem1_uuid),
                            "employee_uuid": str(uuid4()),
                            "user_key": "bar",
                        },
                    ]
                },
                {
                    "objects": [
                        {
                            "itsystem_uuid": str(itsystem2_uuid),
                            "employee_uuid": str(uuid4()),
                            "user_key": "foo",
                        }
                    ]
                },
            ]
        }
    }

    dataloader.query_mo_paged = AsyncMock()  # type: ignore
    dataloader.query_mo_paged.return_value = result

    output = await dataloader.load_all_it_users(itsystem1_uuid)

    assert len(output) == 2
    assert output[0]["itsystem_uuid"] == str(itsystem1_uuid)
    assert output[1]["itsystem_uuid"] == str(itsystem1_uuid)
    assert output[0]["user_key"] == "mucki"
    assert output[1]["user_key"] == "bar"

    output = await dataloader.load_all_it_users(itsystem2_uuid)

    assert len(output) == 1
    assert output[0]["itsystem_uuid"] == str(itsystem2_uuid)
    assert output[0]["user_key"] == "foo"


async def test_query_mo_paged(dataloader: DataLoader):
    employee1 = {"uuid": uuid4()}
    employee2 = {"uuid": uuid4()}
    employee3 = {"uuid": uuid4()}

    results = [
        {
            "employees": {
                "objects": [employee1, employee2],
                "page_info": {"next_cursor": "MWq"},
            }
        },
        {"employees": {"objects": [employee3], "page_info": {"next_cursor": None}}},
    ]

    dataloader.query_mo = AsyncMock()  # type: ignore
    dataloader.query_mo.side_effect = results

    query = gql(
        """
        query AllEmployees($cursor: Cursor) {
          itusers (limit: 2, cursor: $cursor) {
            objects {
                uuid
            }
            page_info {
              next_cursor
            }
          }
        }
        """
    )

    output = await dataloader.query_mo_paged(query)

    uuids = [res["uuid"] for res in output["employees"]["objects"]]

    assert employee1["uuid"] in uuids
    assert employee2["uuid"] in uuids
    assert employee3["uuid"] in uuids


def test_extract_latest_object(dataloader: DataLoader):
    uuid_obj1 = str(uuid4())
    uuid_obj2 = str(uuid4())
    uuid_obj3 = str(uuid4())

    datetime_mock = MagicMock(datetime)
    datetime_mock.datetime.utcnow.return_value = datetime.datetime(2022, 8, 10)
    with patch(
        "mo_ldap_import_export.dataloaders.datetime",
        datetime_mock,
    ):
        # One of the objects is valid today - return it
        objects = [
            {
                "validity": {
                    "from": "2022-08-01T00:00:00+02:00",
                    "to": "2022-08-02T00:00:00+02:00",
                },
                "uuid": uuid_obj1,
            },
            {
                "validity": {
                    "from": "2022-08-02T00:00:00+02:00",
                    "to": "2022-08-15T00:00:00+02:00",
                },
                "uuid": uuid_obj2,
            },
            {
                "validity": {
                    "from": "2022-08-15T00:00:00+02:00",
                    "to": None,
                },
                "uuid": uuid_obj3,
            },
        ]
        assert dataloader.extract_current_or_latest_object(objects)["uuid"] == uuid_obj2

        # No object is valid today - return the latest
        objects = [
            {
                "validity": {
                    "from": "2022-08-01T00:00:00+02:00",
                    "to": "2022-08-02T00:00:00+02:00",
                },
                "uuid": uuid_obj1,
            },
            {
                "validity": {
                    "from": "2022-08-15T00:00:00+02:00",
                    "to": None,
                },
                "uuid": uuid_obj3,
            },
        ]
        assert dataloader.extract_current_or_latest_object(objects)["uuid"] == uuid_obj3

        # No valid current object - return the latest
        objects = [
            {
                "validity": {
                    "from": "2022-08-01T00:00:00+02:00",
                    "to": "2022-08-02T00:00:00+02:00",
                },
                "uuid": uuid_obj1,
            },
            {
                "validity": {
                    "from": "2022-08-15T00:00:00+02:00",
                    "to": "2022-08-20T00:00:00+02:00",
                },
                "uuid": uuid_obj2,
            },
        ]
        assert dataloader.extract_current_or_latest_object(objects)["uuid"] == uuid_obj2

        with pytest.raises(NoObjectsReturnedException):
            objects = []
            dataloader.extract_current_or_latest_object(objects)

        # One of the objects is valid today (without to-date) - return it
        objects = [
            {
                "validity": {
                    "from": "2022-08-01T00:00:00+02:00",
                    "to": "2022-08-02T00:00:00+02:00",
                },
                "uuid": uuid_obj1,
            },
            {
                "validity": {
                    "from": "2022-08-02T00:00:00+02:00",
                    "to": None,
                },
                "uuid": uuid_obj2,
            },
        ]
        assert dataloader.extract_current_or_latest_object(objects)["uuid"] == uuid_obj2

        # One of the objects is valid today (without from-date)- return it
        objects = [
            {
                "validity": {
                    "from": None,
                    "to": "2022-08-15T00:00:00+02:00",
                },
                "uuid": uuid_obj2,
            },
            {
                "validity": {
                    "from": "2022-08-15T00:00:00+02:00",
                    "to": None,
                },
                "uuid": uuid_obj3,
            },
        ]
        assert dataloader.extract_current_or_latest_object(objects)["uuid"] == uuid_obj2


async def test_load_mo_root_org_uuid(dataloader: DataLoader):
    root_org_uuid = uuid4()

    dataloader.query_mo = AsyncMock()  # type: ignore
    dataloader.query_mo.return_value = {"org": {"uuid": str(root_org_uuid)}}

    assert await dataloader.load_mo_root_org_uuid() == str(root_org_uuid)


def test_decompose_ou_string(dataloader: DataLoader):
    ou = "OU=foo,OU=mucki,OU=bar"
    output = dataloader.decompose_ou_string(ou)

    assert len(output) == 3
    assert output[0] == "OU=foo,OU=mucki,OU=bar"
    assert output[1] == "OU=mucki,OU=bar"
    assert output[2] == "OU=bar"


def test_create_ou(dataloader: DataLoader):
    dataloader.load_ldap_OUs = MagicMock()  # type: ignore
    dataloader.ou_in_ous_to_write_to = MagicMock()  # type: ignore
    dataloader.ou_in_ous_to_write_to.return_value = True

    settings_mock = MagicMock()
    settings_mock.ldap_search_base = "DC=Magenta"
    dataloader.user_context["settings"] = settings_mock  # type: ignore

    dataloader.load_ldap_OUs.return_value = {
        "OU=mucki,OU=bar": {"empty": False},
        "OU=bar": {"empty": False},
    }

    ou = "OU=foo,OU=mucki,OU=bar"
    dataloader.create_ou(ou)
    dataloader.ldap_connection.add.assert_called_once_with(
        "OU=foo,OU=mucki,OU=bar,DC=Magenta", "OrganizationalUnit"
    )

    dataloader.user_context["settings"].add_objects_to_ldap = False

    with pytest.raises(NotEnabledException):
        dataloader.create_ou(ou)

    dataloader.ldap_connection.reset_mock()
    dataloader.user_context["settings"].add_objects_to_ldap = True
    dataloader.ou_in_ous_to_write_to.return_value = False

    dataloader.create_ou(ou)
    dataloader.ldap_connection.add.assert_not_called()


def test_delete_ou(dataloader: DataLoader):
    dataloader.load_ldap_OUs = MagicMock()  # type: ignore
    dataloader.ou_in_ous_to_write_to = MagicMock()  # type: ignore
    dataloader.ou_in_ous_to_write_to.return_value = True

    settings_mock = MagicMock()
    settings_mock.ldap_search_base = "DC=Magenta"
    dataloader.user_context["settings"] = settings_mock  # type: ignore

    dataloader.load_ldap_OUs.return_value = {
        "OU=foo,OU=mucki,OU=bar": {"empty": True},
        "OU=mucki,OU=bar": {"empty": False},
        "OU=bar": {"empty": False},
    }

    ou = "OU=foo,OU=mucki,OU=bar"
    dataloader.delete_ou(ou)
    dataloader.ldap_connection.delete.assert_called_once_with(
        "OU=foo,OU=mucki,OU=bar,DC=Magenta"
    )

    dataloader.ldap_connection.reset_mock()
    dataloader.user_context["settings"].add_objects_to_ldap = True
    dataloader.ou_in_ous_to_write_to.return_value = False

    dataloader.delete_ou(ou)
    dataloader.ldap_connection.delete.assert_not_called()

    # Test that we do not remove the ou-for-new-users
    dataloader.ou_in_ous_to_write_to.return_value = True
    settings_mock.ldap_ou_for_new_users = ou
    dataloader.delete_ou(ou)
    dataloader.ldap_connection.delete.assert_not_called()

    # Test that we do not try to remove an OU which is not in the ou-dict
    dataloader.ou_in_ous_to_write_to.return_value = False
    dataloader.delete_ou("OU=non_existing_OU")
    dataloader.ldap_connection.delete.assert_not_called()


def test_move_ldap_object(dataloader: DataLoader):
    dataloader.ou_in_ous_to_write_to = MagicMock()  # type: ignore
    dataloader.ou_in_ous_to_write_to.return_value = True
    settings_mock = MagicMock()
    dataloader.user_context["settings"] = settings_mock  # type: ignore

    dataloader.log_ldap_response = MagicMock()  # type: ignore
    dataloader.log_ldap_response.return_value = {"description": "success"}

    success = dataloader.move_ldap_object("CN=foo,OU=old_ou", "CN=foo,OU=new_ou")

    dataloader.ldap_connection.modify_dn.assert_called_once_with(
        "CN=foo,OU=old_ou", "CN=foo", new_superior="OU=new_ou"
    )
    assert success is True

    dataloader.ou_in_ous_to_write_to.return_value = False
    success = dataloader.move_ldap_object("CN=foo,OU=old_ou", "CN=foo,OU=new_ou")
    assert success is False

    dataloader.ou_in_ous_to_write_to.return_value = True
    dataloader.user_context["settings"].add_objects_to_ldap = False

    with pytest.raises(NotEnabledException):
        dataloader.move_ldap_object("CN=foo,OU=old_ou", "CN=foo,OU=new_ou")


async def test_find_dn_by_engagement_uuid_uses_single_dn() -> None:
    """If passed a single-item `dns` list, simply return the first (and only) DN in that
    list.
    """

    # Arrange
    dataloader: DataLoader = DataLoader(
        {
            "user_context": {
                "ldap_connection": MagicMock(),
                "legacy_graphql_session": AsyncMock(),
                "converter": AsyncMock(),
            }
        }
    )
    # Act
    dn: str = await dataloader.find_dn_by_engagement_uuid(
        MagicMock(),
        MagicMock(),
        ["CN=foo"],
    )
    # Assert
    assert dn == "CN=foo"


async def test_find_dn_by_engagement_uuid_finds_single_dn() -> None:
    # We can't use the `dataloader` fixture here, as we are testing
    # `DataLoader.find_dn_by_engagement_uuid` itself (which is mocked by the
    # `dataloader` fixture.)

    # Arrange
    engagement_uuid: UUID = uuid4()
    engagement_ref: EngagementRef = EngagementRef(uuid=engagement_uuid)
    it_system_uuid: UUID = uuid4()
    it_user_object_guid: UUID = uuid4()
    dataloader: DataLoader = DataLoader(
        {
            "user_context": {
                "ldap_connection": MagicMock(),
                "legacy_graphql_session": AsyncMock(),
                "converter": AsyncMock(),
            }
        }
    )
    dataloader.get_ldap_it_system_uuid = MagicMock()  # type: ignore
    dataloader.get_ldap_it_system_uuid.return_value = str(it_system_uuid)
    dataloader.load_mo_employee_it_users = AsyncMock()  # type: ignore
    dataloader.load_mo_employee_it_users.return_value = [
        ITUser.from_simplified_fields(
            str(it_user_object_guid),  # user_key
            it_system_uuid,
            "2020-01-01",  # from_date
            engagement_uuid=engagement_uuid,
        )
    ]
    dataloader.get_ldap_dn = MagicMock()  # type: ignore
    dataloader.get_ldap_dn.return_value = "CN=foo"
    dns = MagicMock()
    dns.__contains__.return_value = True

    # Act
    dn: str | None = await dataloader.find_dn_by_engagement_uuid(
        uuid4(), engagement_ref, dns
    )

    # Assert
    assert dn == "CN=foo"


async def test_find_dn_by_engagement_uuid_raises_exception_on_multiple_hits() -> None:
    # We can't use the `dataloader` fixture here, as we are testing
    # `DataLoader.find_dn_by_engagement_uuid` itself (which is mocked by the
    # `dataloader` fixture.)

    # Arrange
    engagement_uuid: UUID = uuid4()
    engagement_ref: EngagementRef = EngagementRef(uuid=engagement_uuid)
    it_system_uuid: UUID = uuid4()
    it_user_object_guid: UUID = uuid4()
    dataloader: DataLoader = DataLoader(
        {
            "user_context": {
                "ldap_connection": MagicMock(),
                "legacy_graphql_session": AsyncMock(),
                "converter": AsyncMock(),
            }
        }
    )
    dataloader.get_ldap_it_system_uuid = MagicMock()  # type: ignore
    dataloader.get_ldap_it_system_uuid.return_value = str(it_system_uuid)
    dataloader.load_mo_employee_it_users = AsyncMock()  # type: ignore
    dataloader.load_mo_employee_it_users.return_value = [
        ITUser.from_simplified_fields(
            str(it_user_object_guid),  # user_key
            it_system_uuid,
            "2020-01-01",  # from_date
            engagement_uuid=engagement_uuid,
        )
    ] * 2
    dataloader.get_ldap_dn = MagicMock()  # type: ignore
    dataloader.get_ldap_dn.return_value = "CN=foo"
    dns = MagicMock()
    dns.__contains__.return_value = True

    # Assert
    with pytest.raises(
        MultipleObjectsReturnedException,
        match=r"More than one matching 'Unique LDAP UUID' IT user found for .*? and .*?",
    ):
        # Act
        await dataloader.find_dn_by_engagement_uuid(uuid4(), engagement_ref, dns)


async def test_find_dn_by_engagement_uuid_raises_exception_if_no_hits() -> None:
    # We can't use the `dataloader` fixture here, as we are testing
    # `DataLoader.find_dn_by_engagement_uuid` itself (which is mocked by the
    # `dataloader` fixture.)

    # Arrange
    engagement_uuid: UUID = uuid4()
    engagement_ref: EngagementRef = EngagementRef(uuid=engagement_uuid)
    it_system_uuid: UUID = uuid4()
    dataloader: DataLoader = DataLoader(
        {
            "user_context": {
                "ldap_connection": MagicMock(),
                "legacy_graphql_session": AsyncMock(),
                "converter": AsyncMock(),
            }
        }
    )
    dataloader.get_ldap_it_system_uuid = MagicMock()  # type: ignore
    dataloader.get_ldap_it_system_uuid.return_value = str(it_system_uuid)
    dataloader.load_mo_employee_it_users = AsyncMock()  # type: ignore
    dataloader.load_mo_employee_it_users.return_value = []

    # Assert
    with pytest.raises(NoObjectsReturnedException):
        # Act
        await dataloader.find_dn_by_engagement_uuid(
            uuid4(), engagement_ref, MagicMock()
        )


async def test_find_mo_engagement_uuid(dataloader: DataLoader) -> None:
    """Check that `find_mo_engagement_uuid` returns the expected engagement UUID, by
    looking at any previously created "ADGUID" `ITUser` objects in MO for the given
    employee.
    """

    # Arrange
    object_guid: UUID = uuid4()
    engagement_uuid: UUID = uuid4()
    mock_ldap_object: LdapObject = LdapObject(
        dn="CN=foo", objectGUID=f"{{{object_guid}}}"
    )
    mock_mo_it_user: dict = {
        "itsystem": {"uuid": dataloader.get_ldap_it_system_uuid()},
        "engagement": [{"uuid": str(engagement_uuid)}],
    }
    mock_mo_response: dict = {"itusers": {"objects": [{"current": mock_mo_it_user}]}}
    with patch.object(dataloader, "load_ldap_object", return_value=mock_ldap_object):
        with patch.object(dataloader, "query_mo", return_value=mock_mo_response):
            # Act
            actual_engagement_uuid = await dataloader.find_mo_engagement_uuid("CN=foo")
            # Assert
            assert actual_engagement_uuid == engagement_uuid

    # Test behavior if MO has no IT users for the given employee
    mock_mo_response = {"itusers": {"objects": []}}
    with patch.object(dataloader, "load_ldap_object", return_value=mock_ldap_object):
        with patch.object(dataloader, "query_mo", return_value=mock_mo_response):
            # Act
            empty = await dataloader.find_mo_engagement_uuid("CN=foo")
            # Assert
            assert empty is None


async def test_create_or_edit_mo_objects_empty(dataloader: DataLoader) -> None:
    # *Empty* list of object/verb pairs.
    await dataloader.create_or_edit_mo_objects([])
    dataloader.context["legacy_model_client"].upload.assert_called_once_with([])
    dataloader.context["legacy_model_client"].edit.assert_called_once_with([])


async def test_create_or_edit_mo_objects(dataloader: DataLoader) -> None:
    # One object is created and another is edited.
    create = MagicMock()
    edit = MagicMock()
    objs = [(create, Verb.CREATE), (edit, Verb.EDIT)]
    await dataloader.create_or_edit_mo_objects(objs)  # type: ignore
    dataloader.context["legacy_model_client"].upload.assert_called_once_with([create])
    dataloader.context["legacy_model_client"].edit.assert_called_once_with([edit])
