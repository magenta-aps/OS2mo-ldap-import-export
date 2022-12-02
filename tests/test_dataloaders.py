# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=protected-access
import asyncio
from collections.abc import Iterator
from typing import Collection
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastramqpi.context import Context
from ramodels.mo.details.address import Address
from ramodels.mo.employee import Employee

from mo_ldap_import_export.config import Settings
from mo_ldap_import_export.dataloaders import DataLoader
from mo_ldap_import_export.dataloaders import LdapObject
from mo_ldap_import_export.exceptions import CprNoNotFound


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
        yield MagicMock()


@pytest.fixture
def gql_client() -> Iterator[AsyncMock]:
    yield AsyncMock()


@pytest.fixture
def gql_client_sync() -> Iterator[MagicMock]:
    yield MagicMock()


@pytest.fixture
def model_client() -> Iterator[AsyncMock]:
    yield AsyncMock()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CLIENT_ID", "foo")
    monkeypatch.setenv("client_secret", "bar")
    monkeypatch.setenv("LDAP_CONTROLLERS", '[{"host": "0.0.0.0"}]')
    monkeypatch.setenv("LDAP_DOMAIN", "LDAP")
    monkeypatch.setenv("LDAP_USER", "foo")
    monkeypatch.setenv("LDAP_PASSWORD", "bar")
    monkeypatch.setenv("LDAP_SEARCH_BASE", "DC=ad,DC=addev")
    monkeypatch.setenv("LDAP_ORGANIZATIONAL_UNIT", "OU=Magenta")

    return Settings()


@pytest.fixture
def converter() -> MagicMock:
    converter_mock = MagicMock()
    converter_mock.find_ldap_object_class.return_value = "user"
    return converter_mock


@pytest.fixture
def context(
    ldap_connection: MagicMock,
    gql_client: AsyncMock,
    model_client: AsyncMock,
    settings: Settings,
    cpr_field: str,
    converter: MagicMock,
    gql_client_sync: MagicMock,
) -> Context:

    return {
        "user_context": {
            "settings": settings,
            "ldap_connection": ldap_connection,
            "gql_client": gql_client,
            "model_client": model_client,
            "cpr_field": cpr_field,
            "converter": converter,
            "gql_client_sync": gql_client_sync,
        },
    }


@pytest.fixture
def get_attribute_types() -> dict:

    attr1_mock = MagicMock()
    attr2_mock = MagicMock()
    attr1_mock.single_value = False
    attr2_mock.single_value = True
    return {
        "attr1": attr1_mock,
        "attr2": attr2_mock,
        "department": MagicMock(),
        "name": MagicMock(),
        "employeeID": MagicMock(),
        "postalAddress": MagicMock(),
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
    cpr_no = "0101012002"

    expected_result = LdapObject(dn=dn, **ldap_attributes)
    ldap_connection.response = [mock_ldap_response(ldap_attributes, dn)]

    output = await asyncio.gather(
        dataloader.load_ldap_cpr_object(cpr_no, "Employee"),
    )

    assert output[0] == expected_result


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


async def test_modify_ldap_employee(
    ldap_connection: MagicMock,
    dataloader: DataLoader,
    ldap_attributes: dict,
) -> None:

    employee = LdapObject(
        dn="CN=Nick Janssen,OU=Users,OU=Magenta,DC=ad,DC=addev",
        cpr="0101011234",
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
            dataloader.upload_ldap_object(employee, "user"),
        )

    assert output == [
        [good_response] * len(allowed_parameters_to_upload)
        + [bad_response] * len(disallowed_parameters_to_upload)
    ]


async def test_create_invalid_ldap_employee(
    ldap_connection: MagicMock,
    dataloader: DataLoader,
    ldap_attributes: dict,
    cpr_field: str,
) -> None:

    ldap_attributes_without_cpr_field = {
        key: value for key, value in ldap_attributes.items() if key != cpr_field
    }

    employee = LdapObject(
        dn="CN=Nick Janssen,OU=Users,OU=Magenta,DC=ad,DC=addev",
        **ldap_attributes_without_cpr_field,
    )

    # Get result from dataloader
    try:
        await asyncio.gather(
            dataloader.upload_ldap_object(employee, "user"),
        )
    except CprNoNotFound as e:
        assert e.status_code == 404
        assert type(e) == CprNoNotFound


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
        dataloader.upload_ldap_object(address, "user"),
    )

    changes = {"postalAddress": [("MODIFY_ADD", "foo")]}
    dn = address.dn
    assert ldap_connection.modify.called_once_with(dn, changes)


async def test_create_ldap_employee(
    ldap_connection: MagicMock,
    dataloader: DataLoader,
    ldap_attributes: dict,
    cpr_field: str,
) -> None:

    employee = LdapObject(
        dn="CN=Nick Janssen,OU=Users,OU=Magenta,DC=ad,DC=addev", **ldap_attributes
    )

    non_existing_object_response = {
        "result": 0,
        "description": "noSuchObject",
        "dn": "",
        "message": "",
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

    parameters_to_upload = [k for k in employee.dict().keys() if k not in ["dn"]]

    results = iter(
        [non_existing_object_response] + [good_response] * len(parameters_to_upload)
    )

    def set_new_result(*args, **kwargs) -> None:
        ldap_connection.result = next(results)

    ldap_connection.modify.side_effect = set_new_result

    # Get result from dataloader
    output = await asyncio.gather(
        dataloader.upload_ldap_object(employee, "user"),
    )

    assert output == [[good_response] * len(parameters_to_upload)]


async def test_load_mo_employee(dataloader: DataLoader, gql_client: AsyncMock) -> None:

    cpr_no = "1407711900"
    uuid = uuid4()

    gql_client.execute.return_value = {
        "employees": [
            {"objects": [{"cpr_no": cpr_no, "uuid": uuid}]},
        ]
    }

    expected_result = [Employee(**{"cpr_no": cpr_no, "uuid": uuid})]

    output = await asyncio.gather(
        dataloader.load_mo_employee(uuid),
    )

    assert output == expected_result


async def test_upload_mo_employee(
    model_client: AsyncMock, dataloader: DataLoader
) -> None:
    """Test that test_upload_mo_employee works as expected."""

    return_values = ["1", None, "3"]
    input_values = [1, 2, 3]
    for input_value, return_value in zip(input_values, return_values):
        model_client.upload.return_value = return_value

        result = await asyncio.gather(
            dataloader.upload_mo_objects([input_value]),
        )
        assert result[0] == return_value
        model_client.upload.assert_called_with([input_value])


async def test_make_overview_entry(dataloader: DataLoader):

    attributes = ["attr1", "attr2"]
    superiors = ["sup1", "sup2"]
    entry = dataloader.make_overview_entry(attributes, superiors)

    assert entry["attributes"] == attributes
    assert entry["superiors"] == superiors


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

    assert output["object1"]["attributes"] == ["attr1", "attr2"]
    assert output["object1"]["superiors"] == ["sup1", "sup2"]
    assert output["object1"]["attribute_types"]["attr1"].single_value is False
    assert output["object1"]["attribute_types"]["attr2"].single_value is True


async def test_get_populated_overview(dataloader: DataLoader):

    overview = {
        "object1": {"attributes": ["attr1", "attr2"], "superiors": ["sup1", "sup2"]}
    }

    responses = [
        {
            "attributes": {
                "attr1": "foo",  # We expect this attribute in the output
                "attr2": None,  # But not this one
            }
        }
    ]

    with patch(
        "mo_ldap_import_export.dataloaders.DataLoader.load_ldap_overview",
        return_value=overview,
    ), patch(
        "mo_ldap_import_export.dataloaders.paged_search",
        return_value=responses,
    ):
        output = dataloader.load_ldap_populated_overview()

    assert output["object1"]["attributes"] == ["attr1"]
    assert output["object1"]["superiors"] == ["sup1", "sup2"]
    assert output["object1"]["attribute_types"]["attr1"].single_value is False


async def test_load_mo_address_types(
    dataloader: DataLoader, gql_client_sync: MagicMock
) -> None:

    uuid = uuid4()
    name = "Email"

    gql_client_sync.execute.return_value = {
        "facets": [
            {"classes": [{"uuid": uuid, "name": name}]},
        ]
    }

    expected_result = {uuid: name}
    output = dataloader.load_mo_address_types()
    assert output == expected_result


async def test_load_mo_address(dataloader: DataLoader, gql_client: AsyncMock) -> None:

    uuid = uuid4()

    address_dict: dict = {
        "value": "foo@bar.dk",
        "uuid": uuid,
        "address_type": {"uuid": uuid},
        "validity": {"from": "2021-01-01 01:00"},
        "person": {"uuid": uuid},
    }

    # Note that 'Address' requires 'person' to be a dict
    expected_result = Address(**address_dict.copy())

    # While graphQL returns it as a list with length 1
    address_dict["person"] = [{"cpr_no": "0101012002", "uuid": uuid}]
    address_dict["address_type"]["name"] = "address"

    gql_client.execute.return_value = {
        "addresses": [
            {"objects": [address_dict]},
        ]
    }

    output = await asyncio.gather(
        dataloader.load_mo_address(uuid),
    )

    address_metadata = {
        "address_type_name": address_dict["address_type"]["name"],
        "employee_cpr_no": address_dict["person"][0]["cpr_no"],
    }

    assert output[0][0] == expected_result
    assert output[0][1] == address_metadata


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

    ldap_objects = [
        # LdapObject(dn="foo", value="New address"),
        LdapObject(dn="foo", value="Old address"),
    ]

    with patch(
        "mo_ldap_import_export.dataloaders.DataLoader.load_ldap_object",
        return_value=LdapObject(dn="foo", value=["New address", "Old address"]),
    ):
        dataloader.cleanup_attributes_in_ldap(ldap_objects)

        changes = {"value": [("MODIFY_DELETE", "Old address")]}
        assert dataloader.ldap_connection.modify.called_once_with("foo", changes)

    # Simulate impossible case - where the value field of the ldap object on the server
    # is not a list
    with patch(
        "mo_ldap_import_export.dataloaders.DataLoader.load_ldap_object",
        return_value=LdapObject(dn="foo", value="New address"),
    ):
        with pytest.raises(Exception):
            dataloader.cleanup_attributes_in_ldap(ldap_objects)
