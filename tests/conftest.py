# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
import datetime
import json
import os
from collections.abc import Iterator
from typing import Any
from typing import Mapping
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import yaml
from more_itertools import one
from ramodels.mo.details.address import Address
from ramodels.mo.details.it_system import ITUser
from ramodels.mo.employee import Employee

from mo_ldap_import_export.config import Settings
from mo_ldap_import_export.ldap_classes import LdapObject
from tests.graphql_mocker import GraphQLMocker


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "envvar(mapping): set the specified environmental variables"
    )


@pytest.fixture(autouse=True)
def load_marked_envvars(
    monkeypatch: pytest.MonkeyPatch,
    request: Any,
) -> Iterator[None]:
    """Fixture to inject environmental variable via pytest.marks.

    Example:
        ```
        @pytest.mark.envvar({"VAR1": "1", "VAR2": 2})
        @pytest.mark.envvar({"VAR3": "3"})
        def test_load_marked_envvars() -> None:
            assert os.environ.get("VAR1") == "1"
            assert os.environ.get("VAR2") == "2"
            assert os.environ.get("VAR3") == "3"
            assert os.environ.get("VAR4") is None
        ```

    Args:
        monkeypatch: The patcher to use for settings the environmental variables.
        request: The pytest request object used to extract markers.

    Yields:
        None, but keeps the settings overrides active.
    """
    envvars: dict[str, str] = {}
    for mark in request.node.iter_markers("envvar"):
        if not mark.args:
            pytest.fail("envvar mark must take an argument")
        if len(mark.args) > 1:
            pytest.fail("envvar mark must take at most one argument")
        argument = one(mark.args)
        if not isinstance(argument, Mapping):
            pytest.fail("envvar mark argument must be a mapping")
        if any(not isinstance(key, str) for key in argument.keys()):
            pytest.fail("envvar mapping keys must be strings")
        if any(not isinstance(value, str) for value in argument.values()):
            pytest.fail("envvar mapping values must be strings")
        envvars.update(**argument)
    for key, value in envvars.items():
        monkeypatch.setenv(key, value)
    yield


@pytest.fixture
def settings_overrides() -> Iterator[dict[str, str]]:
    """Fixture to construct dictionary of minimal overrides for valid settings.

    Yields:
        Minimal set of overrides.
    """
    overrides = {
        "CLIENT_ID": "Foo",
        "CLIENT_SECRET": "bar",
        "LDAP_CONTROLLERS": '[{"host": "localhost"}]',
        "LDAP_DOMAIN": "LDAP",
        "LDAP_USER": "foo",
        "LDAP_PASSWORD": "foo",
        "LDAP_SEARCH_BASE": "DC=ad,DC=addev",
        "DEFAULT_ORG_UNIT_LEVEL": "foo",
        "DEFAULT_ORG_UNIT_TYPE": "foo",
        "FASTRAMQPI__AMQP__URL": "amqp://guest:guest@msg_broker:5672/",
    }
    yield overrides


@pytest.fixture
def load_settings_overrides(
    monkeypatch: pytest.MonkeyPatch,
    settings_overrides: dict[str, str],
) -> Iterator[dict[str, str]]:
    """Fixture to set happy-path settings overrides as environmental variables.

    Note:
        Only loads environmental variables, if variables are not already set.

    Args:
        settings_overrides: The list of settings to load in.
        monkeypatch: Pytest MonkeyPatch instance to set environmental variables.

    Yields:
        Minimal set of overrides.
    """
    for key, value in settings_overrides.items():
        if os.environ.get(key) is None:
            monkeypatch.setenv(key, value)
    yield settings_overrides


@pytest.fixture
def minimal_mapping() -> dict[str, Any]:
    return {
        "ldap_to_mo": {
            "Employee": {
                "objectClass": "ramodels.mo.employee.Employee",
                "_import_to_mo_": "false",
                "cpr_no": "{{ldap.employeeID or None}}",
                "uuid": "{{ employee_uuid or NONE }}",
            }
        },
        "mo_to_ldap": {
            "Employee": {
                "objectClass": "inetOrgPerson",
                "_export_to_ldap_": "false",
                "employeeID": "{{mo_employee.cpr_no or None}}",
            }
        },
        "username_generator": {"objectClass": "UserNameGenerator"},
    }


@pytest.fixture
def minimal_valid_environmental_variables(
    load_settings_overrides: dict[str, str],
    minimal_mapping: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    monkeypatch.setenv("CONVERSION_MAPPING", json.dumps(minimal_mapping))
    yield


@pytest.fixture
def minimal_valid_settings(minimal_valid_environmental_variables: None) -> Settings:
    return Settings()


@pytest.fixture
def test_mo_address() -> Address:
    test_mo_address = Address.from_simplified_fields(
        "foo@bar.dk", uuid4(), "2021-01-01"
    )
    return test_mo_address


@pytest.fixture
def test_mo_objects() -> list:
    return [
        {
            "uuid": uuid4(),
            "service_type": "employee",
            "payload": uuid4(),
            "parent_uuid": uuid4(),
            "object_type": "person",
            "validity": {
                "from": datetime.datetime.today().strftime("%Y-%m-%d"),
                "to": None,
            },
        },
        {
            "uuid": uuid4(),
            "service_type": "employee",
            "payload": uuid4(),
            "parent_uuid": uuid4(),
            "object_type": "person",
            "validity": {
                "from": "2021-01-01",
                "to": datetime.datetime.today().strftime("%Y-%m-%d"),
            },
        },
        {
            "uuid": uuid4(),
            "service_type": "employee",
            "payload": uuid4(),
            "parent_uuid": uuid4(),
            "object_type": "person",
            "validity": {
                "from": "2021-01-01",
                "to": "2021-05-01",
            },
        },
        {
            "uuid": uuid4(),
            "service_type": "employee",
            "payload": uuid4(),
            "parent_uuid": uuid4(),
            "object_type": "person",
            "validity": {
                "from": datetime.datetime.today().strftime("%Y-%m-%d"),
                "to": datetime.datetime.today().strftime("%Y-%m-%d"),
            },
        },
    ]


@pytest.fixture
def dataloader(
    sync_dataloader: MagicMock, test_mo_address: Address, test_mo_objects: list
) -> AsyncMock:
    test_ldap_object = LdapObject(
        name="Tester", Department="QA", dn="someDN", EmployeeID="0101012002"
    )
    test_mo_employee = Employee(cpr_no="1212121234")

    test_mo_it_user = ITUser.from_simplified_fields("foo", uuid4(), "2021-01-01")

    load_ldap_cpr_object = AsyncMock()
    load_ldap_cpr_object.return_value = test_ldap_object

    dataloader = AsyncMock()
    dataloader.load_ldap_object = AsyncMock()
    dataloader.load_ldap_OUs = sync_dataloader
    dataloader.load_ldap_populated_overview = sync_dataloader
    dataloader.load_ldap_overview = sync_dataloader
    dataloader.load_ldap_cpr_object = load_ldap_cpr_object
    dataloader.load_ldap_objects.return_value = [test_ldap_object] * 3
    dataloader.load_mo_employee.return_value = test_mo_employee
    dataloader.load_mo_address.return_value = test_mo_address
    dataloader.load_mo_it_user.return_value = test_mo_it_user
    dataloader.load_mo_employee_address_types.return_value = {}
    dataloader.load_mo_org_unit_address_types.return_value = {}
    dataloader.load_mo_it_systems.return_value = {}
    dataloader.load_mo_primary_types.return_value = {}
    dataloader.load_mo_employee_addresses.return_value = [test_mo_address] * 2
    dataloader.load_all_mo_objects.return_value = test_mo_objects
    dataloader.load_mo_object.return_value = test_mo_objects[0]
    dataloader.load_ldap_attribute_values = AsyncMock()
    dataloader.modify_ldap_object.return_value = [{"description": "success"}]
    dataloader.get_ldap_objectGUID = sync_dataloader

    dataloader.load_ldap_OUs = AsyncMock()
    dataloader.move_ldap_object = AsyncMock()
    dataloader.delete_ou = AsyncMock()
    dataloader.create_ou = AsyncMock()

    return dataloader


@pytest.fixture
def sync_dataloader() -> MagicMock:
    dataloader = MagicMock()
    return dataloader


@pytest.fixture
def graphql_mock(respx_mock) -> Iterator[GraphQLMocker]:
    yield GraphQLMocker(respx_mock)


@pytest.fixture
def converter() -> MagicMock:
    converter = MagicMock()
    converter.get_accepted_json_keys.return_value = [
        "Employee",
        "Address",
        "EmailEmployee",
    ]
    converter.cpr_field = "EmployeeID"
    converter._import_to_mo_ = MagicMock()
    converter._import_to_mo_.return_value = True

    converter.to_ldap = AsyncMock()
    converter.from_ldap = AsyncMock()
    converter.to_ldap.return_value = LdapObject(dn="CN=foo", name="Angus")

    converter.get_employee_address_type_user_key = AsyncMock()
    converter.get_org_unit_address_type_user_key = AsyncMock()
    converter.get_it_system_user_key = AsyncMock()
    converter.get_engagement_type_name = AsyncMock()
    converter.get_job_function_name = AsyncMock()
    converter.get_org_unit_name = AsyncMock()

    return converter


@pytest.fixture
def settings() -> MagicMock:
    return MagicMock()


@pytest.fixture
def sync_tool() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def export_checks() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def import_checks() -> AsyncMock:
    return AsyncMock()


def read_mapping(filename):
    """
    Read a json mapping file
    """
    file_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "mo_ldap_import_export",
        "mappings",
        filename,
    )
    with open(file_path) as file:
        return yaml.safe_load(file)
