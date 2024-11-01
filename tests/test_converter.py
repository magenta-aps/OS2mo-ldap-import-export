# SPDX-FileCopyrightText: Magenta ApS <https://magenta.dk>
# SPDX-License-Identifier: MPL-2.0
import datetime
import json
import uuid
from functools import partial
from typing import Any
from typing import cast
from unittest.mock import ANY
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastramqpi.context import Context
from freezegun import freeze_time
from jinja2 import Environment
from jinja2 import Undefined
from mergedeep import Strategy  # type: ignore
from mergedeep import merge
from more_itertools import one
from pydantic import ValidationError
from pydantic import parse_obj_as
from structlog.testing import capture_logs

from mo_ldap_import_export.autogenerated_graphql_client.client import GraphQLClient
from mo_ldap_import_export.autogenerated_graphql_client.read_class_uuid_by_facet_and_class_user_key import (
    ReadClassUuidByFacetAndClassUserKeyClasses,
)
from mo_ldap_import_export.config import ConversionMapping
from mo_ldap_import_export.config import Settings
from mo_ldap_import_export.converters import LdapConverter
from mo_ldap_import_export.environments import _create_facet_class
from mo_ldap_import_export.environments import create_org_unit
from mo_ldap_import_export.environments import get_employee_address_type_uuid
from mo_ldap_import_export.environments import get_employee_dict
from mo_ldap_import_export.environments import get_job_function_name
from mo_ldap_import_export.environments import get_or_create_job_function_uuid
from mo_ldap_import_export.environments import get_org_unit_name
from mo_ldap_import_export.environments import get_org_unit_uuid_from_path
from mo_ldap_import_export.environments import get_visibility_uuid
from mo_ldap_import_export.exceptions import IncorrectMapping
from mo_ldap_import_export.exceptions import NoObjectsReturnedException
from mo_ldap_import_export.exceptions import UUIDNotFoundException
from mo_ldap_import_export.ldap_classes import LdapObject
from mo_ldap_import_export.moapi import MOAPI
from mo_ldap_import_export.utils import MO_TZ
from tests.graphql_mocker import GraphQLMocker

overlay = partial(merge, strategy=Strategy.TYPESAFE_ADDITIVE)


@pytest.fixture
def address_type_uuid() -> str:
    return "f55abef6-5cb6-4c7e-9a62-ed4ab9371a72"


@pytest.fixture
def converter_mapping() -> dict[str, Any]:
    return {
        "ldap_to_mo": {
            "Employee": {
                "objectClass": "ramodels.mo.employee.Employee",
                "_import_to_mo_": "True",
                "_ldap_attributes_": ["givenName", "sn", "employeeID"],
                "given_name": "{{ldap.givenName}}",
                "surname": "{{ldap.sn}}",
                "cpr_number": "{{ldap.employeeID or None}}",
                "uuid": "{{ employee_uuid or '' }}",
            },
            "Email": {
                "objectClass": "ramodels.mo.details.address.Address",
                "_import_to_mo_": "True",
                "_ldap_attributes_": ["mail"],
                "value": "{{ldap.mail}}",
                "address_type": "{{ 'f376deb8-4743-4ca6-a047-3241de8fe9d2' }}",
                "person": "{{ employee_uuid or '' }}",
            },
            "Active Directory": {
                "objectClass": "ramodels.mo.details.it_system.ITUser",
                "_import_to_mo_": "True",
                "_ldap_attributes_": ["msSFU30Name"],
                "user_key": "{{ ldap.msSFU30Name or '' }}",
                "itsystem": "{{ get_it_system_uuid(ldap.itSystemName) }}",
                "person": "{{ employee_uuid or '' }}",
            },
        },
        "mo2ldap": """
            {% set mo_employee = load_mo_employee(uuid, current_objects_only=False) %}
            {% set mo_employee_it_user = load_mo_it_user(uuid, "Active Directory") %}
            {{
                {
                    "givenName": mo_employee.given_name,
                    "sn": mo_employee.surname,
                    "displayName": mo_employee.surname + ", " + mo_employee.given_name,
                    "name": mo_employee.given_name + " " + mo_employee.surname,
                    "employeeID": mo_employee.cpr_number or "",
                    "msSFU30Name": mo_employee_it_user.user_key if mo_employee_it_user else [],
                }|tojson
            }}
        """,
    }


@pytest.fixture
def context(
    minimal_valid_environmental_variables: None,
    monkeypatch: pytest.MonkeyPatch,
    address_type_uuid: str,
    converter_mapping: dict[str, Any],
) -> Context:
    monkeypatch.setenv("CONVERSION_MAPPING", json.dumps(converter_mapping))
    monkeypatch.setenv("LDAP_DIALECT", "AD")
    monkeypatch.setenv("LDAP_SEARCH_BASE", "bar")
    monkeypatch.setenv("DEFAULT_ORG_UNIT_TYPE", "Afdeling")
    monkeypatch.setenv("DEFAULT_ORG_UNIT_LEVEL", "N1")
    monkeypatch.setenv("ORG_UNIT_PATH_STRING_SEPARATOR", "\\")

    settings = Settings()

    dataloader = AsyncMock()
    uuid1 = address_type_uuid
    uuid2 = str(uuid4())
    mo_employee_address_types = {
        uuid1: {"uuid": uuid1, "scope": "MAIL", "user_key": "Email"},
    }

    mo_org_unit_address_types = {
        uuid2: {"uuid": uuid2, "scope": "TEXT", "user_key": "Post"},
    }

    ad_uuid = str(uuid4())
    mo_it_systems = {
        ad_uuid: {"uuid": ad_uuid, "user_key": "Active Directory"},
    }

    dataloader.load_mo_employee_address_types.return_value = mo_employee_address_types
    dataloader.load_mo_org_unit_address_types.return_value = mo_org_unit_address_types
    dataloader.load_mo_it_systems.return_value = mo_it_systems

    attribute_dict: dict[str, bool] = {}

    overview = {"user": {"attributes": attribute_dict}}
    dataloader.load_ldap_overview = MagicMock()
    dataloader.load_ldap_overview.return_value = overview

    org_unit_type_uuid = str(uuid4())
    org_unit_level_uuid = str(uuid4())

    async def read_class_uuid_by(
        facet_user_key: str, class_user_key: str
    ) -> ReadClassUuidByFacetAndClassUserKeyClasses:
        mapping = read_class_uuid_by.map  # type: ignore
        uuid = mapping.get((facet_user_key, class_user_key))
        objects = []
        if uuid:
            objects = [{"uuid": uuid}]
        return parse_obj_as(
            ReadClassUuidByFacetAndClassUserKeyClasses, {"objects": objects}
        )

    fake_read_class_uuid_map = {
        ("org_unit_type", "Afdeling"): org_unit_type_uuid,
        ("org_unit_level", "N1"): org_unit_level_uuid,
    }
    read_class_uuid_by.map = fake_read_class_uuid_map  # type: ignore

    graphql_client: AsyncMock = cast(AsyncMock, dataloader.graphql_client)
    graphql_client.read_class_uuid_by_facet_and_class_user_key = read_class_uuid_by

    context: Context = {
        "user_context": {
            "settings": settings,
            "dataloader": dataloader,
            "username_generator": MagicMock(),
            "event_loop": MagicMock(),
        }
    }

    return context


@pytest.fixture
async def converter(context: Context) -> LdapConverter:
    converter = LdapConverter(
        context["user_context"]["settings"],
        context["user_context"]["dataloader"],
    )
    return converter


@pytest.fixture
async def dataloader(context: Context) -> AsyncMock:
    return cast(AsyncMock, context["user_context"]["dataloader"])


@pytest.fixture
async def graphql_client(dataloader: AsyncMock) -> AsyncMock:
    return cast(AsyncMock, dataloader.graphql_client)


@freeze_time("2019-01-01")
async def test_ldap_to_mo(converter: LdapConverter) -> None:
    employee_uuid = uuid4()
    result = await converter.from_ldap(
        LdapObject(
            dn="",
            name="",
            givenName="Tester",
            sn="Testersen",
            objectGUID="{" + str(uuid.uuid4()) + "}",
            employeeID="0101011234",
        ),
        "Employee",
        employee_uuid=employee_uuid,
    )
    employee = one(result)
    assert employee.given_name == "Tester"
    assert employee.surname == "Testersen"
    assert employee.uuid == employee_uuid

    result = await converter.from_ldap(
        LdapObject(
            dn="",
            mail="foo@bar.dk",
        ),
        "Email",
        employee_uuid=employee_uuid,
    )
    mail = result[0]

    assert mail.value == "foo@bar.dk"
    assert mail.person == employee_uuid
    start = mail.validity.dict()["start"].replace(tzinfo=None)

    # Note: Date is always at midnight in MO
    assert start == datetime.datetime(2019, 1, 1, 0, 0, 0)

    mail = await converter.from_ldap(
        LdapObject(
            dn="",
            mail=[],
        ),
        "Email",
        employee_uuid=employee_uuid,
    )

    assert not mail


async def test_ldap_to_mo_dict_error(converter: LdapConverter) -> None:
    converter.mapping = converter._populate_mapping_with_templates(
        {
            "ldap_to_mo": {
                "Active Directory": {
                    "objectClass": "ramodels.mo.details.it_system.ITUser",
                    "user_key": "{{ ldap.msSFU30Name or '' }}",
                    "itsystem": "{ 'hep': 'hey }",  # provokes json error in str_to_dict
                    "person": "{{ dict(uuid=employee_uuid or '') }}",
                }
            }
        },
        Environment(undefined=Undefined, enable_async=True),
    )

    with pytest.raises(IncorrectMapping):
        await converter.from_ldap(
            LdapObject(
                dn="",
                msSFU30Name=["foo", "bar"],
                itSystemName=["Active Directory", "Active Directory"],
            ),
            "Active Directory",
            employee_uuid=uuid4(),
        )


async def test_ldap_to_mo_dict_validation_error(
    monkeypatch: pytest.MonkeyPatch, context: Context
) -> None:
    mapping = {
        "ldap_to_mo": {
            "Employee": {
                "objectClass": "ramodels.mo.employee.Employee",
                "_import_to_mo_": "True",
                "_ldap_attributes_": ["employeeID"],
                "cpr_number": "{{ldap.employeeID or None}}",
                "uuid": "{{ employee_uuid or '' }}",
            },
            "Custom": {
                "objectClass": "Custom.JobTitleFromADToMO",
                "_import_to_mo_": "true",
                "_ldap_attributes_": ["hkStsuuid"],
                "user": "{{ ldap.hkStsuuid }}",
                "job_function": f"{{ {uuid4()} }}",
                "uuid": "{{ employee_uuid or '' }}",
            },
        }
    }
    monkeypatch.setenv("CONVERSION_MAPPING", json.dumps(mapping))
    settings = Settings()
    dataloader = context["user_context"]["dataloader"]

    converter = LdapConverter(settings, dataloader)

    with capture_logs() as cap_logs:
        await converter.from_ldap(
            LdapObject(
                dn="",
                hkStsuuid="not_an_uuid",
                title="job title",
                comment="job title default",
            ),
            "Custom",
            employee_uuid=uuid4(),
        )

        info_messages = [w for w in cap_logs if w["log_level"] == "info"]
        assert "Exception during object parsing" in str(info_messages)


async def test_from_ldap_bad_json_key(converter: LdapConverter) -> None:
    with pytest.raises(IncorrectMapping):
        await converter.from_ldap(
            LdapObject(dn="CN=foo"), "__non_existing_key", uuid4()
        )
    assert "Missing '__non_existing_key' in mapping 'ldap_to_mo'"


@pytest.mark.parametrize(
    "ldap_values,expected",
    (
        # Base case
        ({}, {}),
        # Single overrides
        ({"cpr": "0101700000"}, {"cpr_number": "0101700000"}),
        ({"givenName": "Hans"}, {"given_name": "Hans"}),
        ({"sn": "Petersen"}, {"surname": "Petersen"}),
        # Empty values -> no keys
        ({"cpr": ""}, {}),
        ({"givenName": ""}, {"given_name": None}),
        ({"sn": ""}, {"surname": None}),
    ),
)
async def test_template_strictness(
    monkeypatch: pytest.MonkeyPatch,
    converter: LdapConverter,
    ldap_values: dict[str, str],
    expected: dict[str, str],
) -> None:
    mapping = {
        "ldap_to_mo": {
            "Employee": {
                "objectClass": "ramodels.mo.employee.Employee",
                "_import_to_mo_": "True",
                "_ldap_attributes_": ["givenName", "sn"],
                "user_key": "{{ ldap.dn }}",
                "given_name": "{{ ldap.get('givenName', 'given_name') }}",
                "surname": "{{ ldap.sn if 'sn' in ldap else 'surname' }}",
                "cpr_number": "{{ ldap.get('cpr') }}",
                "uuid": "{{ employee_uuid }}",
            }
        }
    }
    monkeypatch.setenv("CONVERSION_MAPPING", json.dumps(mapping))
    converter = LdapConverter(Settings(), converter.dataloader)
    result = await converter.from_ldap(
        LdapObject(dn="CN=foo", **ldap_values),
        "Employee",
        employee_uuid=uuid4(),
    )
    employee = one(result)
    expected_employee = {
        "uuid": ANY,
        "user_key": "CN=foo",
        "given_name": "given_name",
        "surname": "surname",
    }
    for key, value in expected.items():
        if value is None:
            del expected_employee[key]
        else:
            expected_employee[key] = value

    assert employee.dict(exclude_unset=True) == expected_employee


def test_get_ldap_attributes(converter: LdapConverter) -> None:
    settings = Settings()
    assert settings.conversion_mapping.ldap_to_mo is not None

    converter_attributes = set(converter.get_ldap_attributes("Employee"))
    settings_attributes = set(
        settings.conversion_mapping.ldap_to_mo["Employee"].ldap_attributes
    )
    assert converter_attributes == settings_attributes


async def test_get_ldap_attributes_dn_removed(
    converter_mapping: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    dataloader: AsyncMock,
) -> None:
    mapping = overlay(
        converter_mapping,
        {
            "ldap_to_mo": {
                "Employee": {
                    "ldap_attributes": (
                        converter_mapping["ldap_to_mo"]["Employee"]["_ldap_attributes_"]
                        + ["dn"]
                    )
                }
            }
        },
    )
    monkeypatch.setenv("CONVERSION_MAPPING", json.dumps(mapping))

    settings = Settings()
    assert settings.conversion_mapping.ldap_to_mo is not None

    converter = LdapConverter(settings, dataloader)

    converter_attributes = set(converter.get_ldap_attributes("Employee"))
    settings_attributes = set(
        settings.conversion_mapping.ldap_to_mo["Employee"].ldap_attributes
    )
    assert converter_attributes == settings_attributes - {"dn"}


def test_get_mo_attributes(converter: LdapConverter) -> None:
    attributes = set(converter.get_mo_attributes("Employee"))
    assert attributes == {"uuid", "cpr_number", "surname", "given_name"}


def test_str_to_dict(converter: LdapConverter):
    output = converter.str_to_dict("{'foo':2}")
    assert output == {"foo": 2}

    output = converter.str_to_dict("{'foo':Undefined}")
    assert output == {"foo": None}


@pytest.mark.parametrize(
    "ldap_object,expected",
    [
        (LdapObject(dn="foo"), 1),
        (LdapObject(dn="foo", value=[]), 1),
        (LdapObject(dn="foo", value=[], value2=[]), 1),
        (LdapObject(dn="foo", value=["bar"]), 1),
        (LdapObject(dn="foo", value=["bar"], value2=[]), 1),
        (LdapObject(dn="foo", value=["bar", "baz"]), 2),
        (LdapObject(dn="foo", value=["bar", "baz"], value2=[]), 2),
        (LdapObject(dn="foo", value=["bar"], value2=["baz"]), 1),
        (LdapObject(dn="foo", value=["bar", "baz", "qux"]), 3),
        (LdapObject(dn="foo", value=["bar", "baz", "qux"], value2=[]), 3),
        (LdapObject(dn="foo", value=["bar", "baz", "qux"], value2=["quux"]), 3),
        (LdapObject(dn="foo", value=["bar", "baz"], value2=["qux", "quux"]), 2),
    ],
)
def test_get_number_of_entries(
    converter: LdapConverter, ldap_object: LdapObject, expected: int
) -> None:
    assert converter.get_number_of_entries(ldap_object) == expected


EMPLOYEE_OBJ = {
    "objectClass": "ramodels.mo.employee.Employee",
    "_ldap_attributes_": [],
    "uuid": "{{ employee_uuid }}",
}


@pytest.mark.parametrize("class_name", ["foo", "bar"])
async def test_get_employee_address_type_uuid(
    graphql_client: AsyncMock, class_name: str
) -> None:
    class_uuid = str(uuid4())

    graphql_client.read_class_uuid_by_facet_and_class_user_key.map[
        ("employee_address_type", class_name)
    ] = class_uuid
    assert (
        await get_employee_address_type_uuid(graphql_client, class_name) == class_uuid
    )


@pytest.mark.parametrize("class_name", ["Hemmelig", "Offentlig"])
async def test_get_visibility_uuid(graphql_client: AsyncMock, class_name: str) -> None:
    class_uuid = str(uuid4())

    graphql_client.read_class_uuid_by_facet_and_class_user_key.map[
        ("visibility", class_name)
    ] = class_uuid
    assert await get_visibility_uuid(graphql_client, class_name) == class_uuid


async def test_get_job_function_uuid(
    graphql_mock: GraphQLMocker, dataloader: AsyncMock
) -> None:
    graphql_client = GraphQLClient("http://example.com/graphql")
    dataloader.graphql_client = graphql_client

    route = graphql_mock.query("read_class_uuid_by_facet_and_class_user_key")

    uuid1 = str(uuid4())
    route.result = {"classes": {"objects": [{"uuid": uuid1}]}}
    assert await get_or_create_job_function_uuid(dataloader, "Major") == uuid1
    assert route.called
    route.reset()

    uuid2 = str(uuid4())
    route.result = {"classes": {"objects": [{"uuid": uuid2}]}}
    assert await get_or_create_job_function_uuid(dataloader, "Secretary") == uuid2
    assert route.called
    route.reset()

    new_uuid = uuid4()
    dataloader = AsyncMock()
    dataloader.create_mo_class.return_value = new_uuid

    result = await get_or_create_job_function_uuid(dataloader, "non-existing_job")
    assert result == str(new_uuid)

    with pytest.raises(UUIDNotFoundException):
        await get_or_create_job_function_uuid(dataloader, "")

    with pytest.raises(UUIDNotFoundException):
        await get_or_create_job_function_uuid(dataloader, [])  # type: ignore


async def test_get_job_function_uuid_default_kwarg(dataloader: AsyncMock) -> None:
    """Test that a provided `default` is used if the value of `job_function` is falsy."""
    # Arrange: mock the UUID of a newly created job function
    uuid_for_new_job_function = str(uuid4())
    dataloader = AsyncMock()
    dataloader.create_mo_class.return_value = uuid_for_new_job_function

    # Act
    result = await get_or_create_job_function_uuid(dataloader, "", default="Default")

    # Assert
    assert result == uuid_for_new_job_function


async def test_get_job_function_uuid_default_kwarg_does_not_override(
    dataloader: AsyncMock,
) -> None:
    """Test that a provided `default` is *not* used if the value of `job_function` is
    truthy."""
    # Arrange
    uuid = str(uuid4())
    dataloader = AsyncMock()
    dataloader.create_mo_class.return_value = uuid

    # Act
    result = await get_or_create_job_function_uuid(
        dataloader, "Something", default="Default"
    )

    # Assert
    assert result == uuid


@pytest.mark.parametrize("class_name", ["Major", "Secretary"])
async def test_get_job_function_name(
    graphql_mock: GraphQLMocker, class_name: str
) -> None:
    graphql_client = GraphQLClient("http://example.com/graphql")

    route = graphql_mock.query("read_class_name_by_class_uuid")
    route.result = {"classes": {"objects": [{"current": {"name": class_name}}]}}

    class_uuid = uuid4()
    assert await get_job_function_name(graphql_client, class_uuid) == class_name
    assert route.called

    route.reset()
    route.result = {"classes": {"objects": [{"current": None}]}}
    with pytest.raises(NoObjectsReturnedException) as exc_info:
        await get_job_function_name(graphql_client, class_uuid)
    assert f"job_function not active, uuid: {class_uuid}" in str(exc_info.value)
    assert route.called


@pytest.mark.parametrize("org_unit_name", ["IT Support", "Digitalization"])
async def test_get_org_unit_name(
    graphql_mock: GraphQLMocker, org_unit_name: str
) -> None:
    graphql_client = GraphQLClient("http://example.com/graphql")

    route = graphql_mock.query("read_org_unit_name")
    route.result = {"org_units": {"objects": [{"current": {"name": org_unit_name}}]}}

    org_unit_uuid = uuid4()
    assert await get_org_unit_name(graphql_client, org_unit_uuid) == org_unit_name
    assert route.called

    route.reset()
    route.result = {"org_units": {"objects": [{"current": None}]}}
    with pytest.raises(NoObjectsReturnedException) as exc_info:
        await get_org_unit_name(graphql_client, org_unit_uuid)
    assert f"org_unit not active, uuid: {org_unit_uuid}" in str(exc_info.value)
    assert route.called


@pytest.mark.parametrize("it_system_user_key", ["AD", "Plone"])
async def test_get_it_system_uuid(
    settings_mock: Settings, graphql_mock: GraphQLMocker, it_system_user_key: str
) -> None:
    graphql_client = GraphQLClient("http://example.com/graphql")

    it_system_uuid = uuid4()
    route = graphql_mock.query("read_itsystem_uuid")
    route.result = {"itsystems": {"objects": [{"uuid": it_system_uuid}]}}

    assert await MOAPI(settings_mock, graphql_client).get_it_system_uuid(
        it_system_user_key
    ) == str(it_system_uuid)
    assert route.called

    route.reset()
    route.result = {"itsystems": {"objects": []}}
    with pytest.raises(UUIDNotFoundException) as exc_info:
        await MOAPI(settings_mock, graphql_client).get_it_system_uuid(
            it_system_user_key
        )
    assert f"itsystem not found, user_key: {it_system_user_key}" in str(exc_info.value)
    assert route.called


async def test_create_org_unit_already_exists(
    graphql_mock: GraphQLMocker, converter: LdapConverter
) -> None:
    graphql_client = GraphQLClient("http://example.com/graphql")
    converter.dataloader.graphql_client = graphql_client  # type: ignore

    route = graphql_mock.query("read_org_unit_uuid")
    route.result = {"org_units": {"objects": [{"uuid": uuid4()}]}}

    dataloader = converter.dataloader
    settings = converter.settings
    await create_org_unit(dataloader, settings, ["Magenta Aps", "Magenta Aarhus"])
    converter.dataloader.create_org_unit.assert_not_called()  # type: ignore


@pytest.mark.parametrize(
    "path,expected",
    [
        (["Magenta Aps"], 1),
        (["Magenta Aps", "Magenta Aarhus"], 2),
        (["Magenta Aps", "Magenta Aarhus", "OS2mo"], 3),
    ],
)
async def test_create_org_unit_all_missing(
    graphql_mock: GraphQLMocker,
    converter: LdapConverter,
    path: list[str],
    expected: int,
) -> None:
    graphql_client = GraphQLClient("http://example.com/graphql")
    converter.dataloader.graphql_client = graphql_client  # type: ignore

    route1 = graphql_mock.query("read_org_unit_uuid")
    route1.result = {"org_units": {"objects": []}}

    route2 = graphql_mock.query("read_class_uuid_by_facet_and_class_user_key")
    route2.result = {"classes": {"objects": [{"uuid": uuid4()}]}}

    route3 = graphql_mock.query("read_root_org_uuid")
    route3.result = {"org": {"uuid": uuid4()}}

    dataloader = converter.dataloader
    settings = converter.settings
    await create_org_unit(dataloader, settings, path)
    num_calls = len(converter.dataloader.create_org_unit.mock_calls)  # type: ignore
    assert num_calls == expected


def test_check_uuid_refs_in_mo_objects(converter_mapping: dict[str, Any]) -> None:
    address_obj = {
        "objectClass": "ramodels.mo.details.address.Address",
        "_import_to_mo_": "true",
        "_ldap_attributes_": [],
        "value": "val",
        "validity": "val",
        "address_type": "val",
    }

    converter_mapping.update(
        {
            "ldap_to_mo": {
                "EmailEmployee": {
                    **address_obj,
                }
            }
        }
    )
    with pytest.raises(
        ValidationError, match="Either 'person' or 'org_unit' key needs to be present"
    ):
        parse_obj_as(ConversionMapping, converter_mapping)

    converter_mapping.update(
        {
            "ldap_to_mo": {
                "EmailEmployee": {
                    **address_obj,
                    "person": "{{ employee_uuid or '' }}",
                    "org_unit": "{{ employee_uuid or '' }}",
                }
            }
        }
    )
    with pytest.raises(
        ValidationError,
        match="Either 'person' or 'org_unit' key needs to be present.*Not both",
    ):
        parse_obj_as(ConversionMapping, converter_mapping)

    converter_mapping.update(
        {
            "ldap_to_mo": {
                "Employee": {
                    "objectClass": "ramodels.mo.employee.Employee",
                    "_import_to_mo_": "true",
                }
            }
        }
    )
    with pytest.raises(ValidationError, match="Needs to contain a key called 'uuid'"):
        parse_obj_as(ConversionMapping, converter_mapping)


@pytest.mark.usefixtures("minimal_valid_environmental_variables")
@pytest.mark.parametrize(
    "import_to_mo,is_ok",
    [
        ("True", True),
        ("False", True),
        ("manual_import_only", True),
        ("manual_import", False),
        ("ldap_please_import", False),
        ("car_license_expired", False),
    ],
)
def test_import_to_mo_configuration(
    monkeypatch: pytest.MonkeyPatch,
    import_to_mo: str,
    is_ok: bool,
) -> None:
    monkeypatch.setenv(
        "CONVERSION_MAPPING",
        json.dumps(
            {
                "ldap_to_mo": {
                    "Employee": {
                        "objectClass": "ramodels.mo.employee.Employee",
                        "_import_to_mo_": import_to_mo,
                        "_ldap_attributes_": [],
                        "uuid": "{{ employee_uuid or '' }}",
                    }
                },
                "username_generator": {"objectClass": "UserNameGenerator"},
            }
        ),
    )
    if is_ok:
        Settings()
    else:
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        expected_strings = [
            "1 validation error for Settings",
            "conversion_mapping -> ldap_to_mo -> Employee -> _import_to_mo",
            "unexpected value; permitted: 'true', 'false', 'manual_import_only'",
            f"given={import_to_mo}",
        ]
        for expected in expected_strings:
            assert expected in str(exc_info.value)


@pytest.mark.usefixtures("minimal_valid_environmental_variables")
@pytest.mark.parametrize(
    "import_to_mo,manual_import,expected",
    [
        ("True", False, True),
        ("True", True, True),
        ("False", False, False),
        ("False", True, False),
        ("manual_import_only", False, False),
        ("manual_import_only", True, True),
    ],
)
def test_import_to_mo(
    monkeypatch: pytest.MonkeyPatch,
    import_to_mo: str,
    manual_import: bool,
    expected: bool,
) -> None:
    monkeypatch.setenv(
        "CONVERSION_MAPPING",
        json.dumps(
            {
                "ldap_to_mo": {
                    "Employee": {
                        "objectClass": "ramodels.mo.employee.Employee",
                        "_import_to_mo_": import_to_mo,
                        "_ldap_attributes_": [],
                        "uuid": "{{ employee_uuid or '' }}",
                    }
                },
                "username_generator": {"objectClass": "UserNameGenerator"},
            }
        ),
    )

    settings = Settings()
    assert settings.conversion_mapping.ldap_to_mo is not None
    employee_mapping = settings.conversion_mapping.ldap_to_mo["Employee"]

    assert (
        employee_mapping.import_to_mo_as_bool(manual_import=manual_import) is expected
    )


@pytest.mark.parametrize(
    "overlay,expected",
    [
        (
            {
                "ldap_to_mo": {
                    "Employee": {**EMPLOYEE_OBJ, "_import_to_mo_": "f"},
                },
            },
            "unexpected value; permitted: ",
        ),
        (
            {
                "ldap_to_mo": {
                    "Employee": EMPLOYEE_OBJ,
                },
            },
            "_import_to_mo_\n  field required",
        ),
        (
            {
                "ldap_to_mo": {
                    "Employee": {**EMPLOYEE_OBJ, "_import_to_mo_": "True"},
                },
            },
            None,
        ),
    ],
)
def test_check_import_and_export_flags(
    converter_mapping: dict[str, Any],
    overlay: dict[str, Any],
    expected: str | None,
) -> None:
    converter_mapping.update(overlay)
    if expected:
        with pytest.raises(ValidationError, match=expected):
            parse_obj_as(ConversionMapping, converter_mapping)
    else:
        parse_obj_as(ConversionMapping, converter_mapping)


async def test_get_org_unit_uuid_from_path(graphql_mock: GraphQLMocker) -> None:
    org_unit_uuid = uuid4()

    graphql_client = GraphQLClient("http://example.com/graphql")

    route = graphql_mock.query("read_org_unit_uuid")
    route.result = {"org_units": {"objects": [{"uuid": org_unit_uuid}]}}

    result = await get_org_unit_uuid_from_path(graphql_client, ["org1", "org2", "org3"])
    assert result == org_unit_uuid
    call_content = json.loads(one(route.calls).request.content)
    filter = call_content["variables"]["filter"]
    assert filter == {
        "names": ["org3"],
        "parent": {"names": ["org2"], "parent": {"names": ["org1"], "parent": None}},
    }


async def test_get_org_unit_uuid_from_path_no_match(
    graphql_mock: GraphQLMocker,
) -> None:
    graphql_client = GraphQLClient("http://example.com/graphql")

    route = graphql_mock.query("read_org_unit_uuid")
    route.result = {"org_units": {"objects": []}}

    with pytest.raises(UUIDNotFoundException) as exc_info:
        await get_org_unit_uuid_from_path(graphql_client, ["org1", "org4"])
    assert "['org1', 'org4'] not found in OS2mo" in str(exc_info.value)

    call_content = json.loads(one(route.calls).request.content)
    filter = call_content["variables"]["filter"]
    assert filter == {"names": ["org4"], "parent": {"names": ["org1"], "parent": None}}


async def test_get_employee_dict_no_employee(
    settings_mock: Settings, graphql_mock: GraphQLMocker, dataloader: AsyncMock
) -> None:
    graphql_client = GraphQLClient("http://example.com/graphql")
    dataloader.graphql_client = graphql_client
    dataloader.moapi = MOAPI(settings_mock, graphql_client)

    route = graphql_mock.query("read_employees")
    route.result = {"employees": {"objects": []}}

    employee_uuid = uuid4()

    with pytest.raises(NoObjectsReturnedException) as exc_info:
        await get_employee_dict(dataloader, employee_uuid)
    assert f"Unable to lookup employee: {employee_uuid}" in str(exc_info.value)


async def test_get_employee_dict(
    settings_mock: Settings, graphql_mock: GraphQLMocker, dataloader: AsyncMock
) -> None:
    graphql_client = GraphQLClient("http://example.com/graphql")
    dataloader.graphql_client = graphql_client
    dataloader.moapi = MOAPI(settings_mock, graphql_client)

    cpr_number = "1407711900"
    uuid = uuid4()

    route = graphql_mock.query("read_employees")
    route.result = {
        "employees": {
            "objects": [
                {
                    "validities": [
                        {
                            "uuid": uuid,
                            "cpr_number": cpr_number,
                            "given_name": "Hans",
                            "surname": "Andersen",
                            "nickname_given_name": None,
                            "nickname_surname": None,
                            "validity": {
                                "from": None,
                                "to": None,
                            },
                        }
                    ]
                }
            ]
        }
    }

    result = await get_employee_dict(dataloader, uuid)
    assert result == {
        "given_name": "Hans",
        "nickname_given_name": None,
        "nickname_surname": None,
        "seniority": None,
        "surname": "Andersen",
        "user_key": str(uuid),
        "uuid": uuid,
        "cpr_number": cpr_number,
    }


async def test_ldap_to_mo_termination(
    monkeypatch: pytest.MonkeyPatch,
    converter_mapping: dict[str, Any],
    dataloader: AsyncMock,
) -> None:
    settings = Settings()
    converter = LdapConverter(settings, dataloader)

    employee_uuid = uuid4()
    result = await converter.from_ldap(
        LdapObject(
            dn="",
            mail="foo@bar.dk",
            mail_validity_from=datetime.datetime(2019, 1, 1, 0, 10, 0),
        ),
        "Email",
        employee_uuid=employee_uuid,
    )
    mail = one(result)
    assert not hasattr(mail, "terminate_")
    assert mail.value == "foo@bar.dk"
    assert mail.person == employee_uuid

    # Add _terminate_ key to Email mapping
    converter_mapping["ldap_to_mo"]["Email"]["_terminate_"] = (
        "{{ now()|mo_datestring }}"
    )
    monkeypatch.setenv("CONVERSION_MAPPING", json.dumps(converter_mapping))
    settings = Settings()
    converter = LdapConverter(settings, dataloader)

    result = await converter.from_ldap(
        LdapObject(
            dn="",
            mail="foo@bar.dk",
            mail_validity_from=datetime.datetime(2019, 1, 1, 0, 10, 0),
        ),
        "Email",
        employee_uuid=employee_uuid,
    )
    mail = one(result)
    assert hasattr(mail, "terminate_")
    assert mail.value == "foo@bar.dk"
    assert mail.person == employee_uuid


async def test_create_facet_class_no_facet() -> None:
    dataloader = AsyncMock()
    dataloader.moapi.load_mo_facet_uuid.return_value = None
    with pytest.raises(NoObjectsReturnedException) as exc_info:
        await _create_facet_class(dataloader, "class_key", "facet_key")
    assert "Could not find facet with user_key = 'facet_key'" in str(exc_info.value)


@freeze_time("2022-08-10T12:34:56")
async def test_ldap_to_mo_default_validity(converter: LdapConverter) -> None:
    employee_uuid = uuid4()
    result = await converter.from_ldap(
        LdapObject(
            dn="",
            mail="foo@bar.dk",
        ),
        "Email",
        employee_uuid=employee_uuid,
    )
    mail = one(result)
    assert mail.value == "foo@bar.dk"
    assert mail.person == employee_uuid
    assert mail.validity.dict() == {
        "start": datetime.datetime(2022, 8, 10, 0, 0, tzinfo=MO_TZ),
        "end": None,
    }


@freeze_time("2022-08-10")
async def test_ldap_to_mo_mapper(
    monkeypatch: pytest.MonkeyPatch,
    converter_mapping: dict[str, Any],
    dataloader: AsyncMock,
) -> None:
    """Ensure that setting mapper has no effect on construction objects.

    Injector is only used for creating an mapping between objects later.
    """

    mapper_template = "{{ value['user_key'] }}"
    converter_mapping["ldap_to_mo"]["Email"]["_mapper_"] = mapper_template
    monkeypatch.setenv("CONVERSION_MAPPING", json.dumps(converter_mapping))
    settings = Settings()
    converter = LdapConverter(settings, dataloader)

    employee_uuid = uuid4()
    result = await converter.from_ldap(
        LdapObject(
            dn="",
            mail="foo@bar.dk",
            mail_validity_from=datetime.datetime(2019, 1, 1, 0, 10, 0),
        ),
        "Email",
        employee_uuid=employee_uuid,
    )
    mail = one(result)
    assert mail.value == "foo@bar.dk"
    assert mail.person == employee_uuid
