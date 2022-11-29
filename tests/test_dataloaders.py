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

import pytest
from fastramqpi.context import Context

from mo_ldap_import_export.config import Settings
from mo_ldap_import_export.dataloaders import DataLoader
from mo_ldap_import_export.dataloaders import LdapObject

# from uuid import uuid4
# from more_itertools import collapse
# from ramodels.mo.employee import Employee
# from mo_ldap_import_export.dataloaders import get_ldap_attributes

# from mo_ldap_import_export.exceptions import CprNoNotFound
# from mo_ldap_import_export.exceptions import MultipleObjectsReturnedException
# from mo_ldap_import_export.exceptions import NoObjectsReturnedException
# from mo_ldap_import_export.ldap import paged_search


@pytest.fixture()
def ldap_attributes() -> dict:
    return {"department": None, "name": "John", "employeeID": "0101011234"}


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
) -> Context:

    return {
        "user_context": {
            "settings": settings,
            "ldap_connection": ldap_connection,
            "gql_client": gql_client,
            "model_client": model_client,
            "cpr_field": cpr_field,
            "converter": converter,
        },
    }


@pytest.fixture
def dataloader(
    context: Context,
) -> DataLoader:
    """Fixture to construct a dataloaders object using fixture mocks.

    Yields:
        Dataloaders with mocked clients.
    """
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

    expected_result = [LdapObject(dn=dn, **ldap_attributes)]
    ldap_connection.response = [mock_ldap_response(ldap_attributes, dn)]

    output = await asyncio.gather(
        dataloader.load_ldap_cpr_object(cpr_no, "Employee"),
    )

    assert output == expected_result
