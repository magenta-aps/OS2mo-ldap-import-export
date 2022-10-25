# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=protected-access
"""Test ensure_adguid_itsystem."""
import asyncio
from collections.abc import Iterator
from typing import Union
from unittest.mock import MagicMock

import pytest

from mo_ldap_import_export.config import Settings
from mo_ldap_import_export.dataloaders import configure_dataloaders
from mo_ldap_import_export.dataloaders import Dataloaders


@pytest.fixture
def ad_connection() -> Iterator[MagicMock]:
    """Fixture to construct a mock ad_connection.

    Yields:
        A mock for ad_connection.
    """
    yield MagicMock()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CLIENT_ID", "foo")
    monkeypatch.setenv("client_secret", "bar")
    monkeypatch.setenv("AD_CONTROLLERS", '[{"host": "0.0.0.0"}]')
    monkeypatch.setenv("AD_DOMAIN", "AD")
    monkeypatch.setenv("AD_USER", "foo")
    monkeypatch.setenv("AD_PASSWORD", "bar")
    monkeypatch.setenv("AD_SEARCH_BASE", "DC=ad,DC=addev")
    return Settings()


@pytest.fixture
def dataloaders(
    ad_connection: MagicMock,
    settings: Settings,
) -> Iterator[Dataloaders]:
    """Fixture to construct a dataloaders object using fixture mocks.

    Yields:
        Dataloaders with mocked clients.
    """
    dataloaders = configure_dataloaders(
        {
            # "graphql_session": graphql_session,
            "user_context": {
                "settings": settings,
                "ad_connection": ad_connection,
            },
            # "model_client": model_client,
        }
    )
    yield dataloaders


def mock_ad_entry(guid: str, name: str, department: Union[str, None]) -> object:

    # Mock AD entry
    class Entry:
        class objectGUIDClass:
            def __init__(self) -> None:
                self.value: str = guid

        class NameClass:
            def __init__(self) -> None:
                self.value: str = name

        class DepartmentClass:
            def __init__(self) -> None:
                self.value: Union[str, None] = department

        objectGUID: objectGUIDClass = objectGUIDClass()
        Name: NameClass = NameClass()
        Department: DepartmentClass = DepartmentClass()

    return Entry()


async def test_load_adguid(ad_connection: MagicMock, dataloaders: Dataloaders) -> None:
    """Test that load_adguid works as expected."""

    guid = "{b55be9e3-4ca6-45f4-8bd3-3c3c9e15edb1}"
    name = "Nick Janssen"
    department = None

    expected_results = [
        {
            "guid": guid,
            "name": name,
            "department": department,
        }
    ]

    # Mock AD connection
    ad_connection.entries = [mock_ad_entry(guid, name, department)]
    ad_connection.result = {
        "controls": {"1.2.840.113556.1.4.319": {"value": {"cookie": None}}}
    }

    # Get result from dataloader
    results = await asyncio.gather(
        dataloaders.org_persons_loader.load(0),
    )

    assert results == [expected_results]
