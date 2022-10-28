# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=protected-access
"""Test ensure_adguid_itsystem."""
import os
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastramqpi.main import FastRAMQPI

from mo_ldap_import_export.dataloaders import Dataloaders
from mo_ldap_import_export.main import create_app
from mo_ldap_import_export.main import create_fastramqpi
from mo_ldap_import_export.main import open_ad_connection
from mo_ldap_import_export.main import seed_dataloaders


@pytest.fixture
def settings_overrides() -> Iterator[dict[str, str]]:
    """Fixture to construct dictionary of minimal overrides for valid settings.

    Yields:
        Minimal set of overrides.
    """
    overrides = {
        "CLIENT_ID": "Foo",
        "CLIENT_SECRET": "bar",
        "AD_CONTROLLERS": '[{"host": "localhost"}]',
        "AD_DOMAIN": "AD",
        "AD_USER": "foo",
        "AD_PASSWORD": "foo",
        "AD_SEARCH_BASE": "DC=ad,DC=addev",
    }
    yield overrides


@pytest.fixture
def load_settings_overrides(
    settings_overrides: dict[str, str], monkeypatch: pytest.MonkeyPatch
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
        if os.environ.get(key) is not None:
            continue
        monkeypatch.setenv(key, value)
    yield settings_overrides


@pytest.fixture
def disable_metrics(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fixture to set the ENABLE_METRICS environmental variable to False.

    Yields:
        None
    """
    monkeypatch.setenv("ENABLE_METRICS", "False")
    yield


@pytest.fixture
def fastramqpi(
    disable_metrics: None, load_settings_overrides: dict[str, str]
) -> Iterator[FastRAMQPI]:
    """Fixture to construct a FastRAMQPI system.

    Yields:
        FastRAMQPI system.
    """
    with patch(
        "mo_ldap_import_export.main.configure_ad_connection", new_callable=MagicMock
    ):
        yield create_fastramqpi()


@pytest.fixture
def app(fastramqpi: FastRAMQPI) -> Iterator[FastAPI]:
    """Fixture to construct a FastAPI application.

    Yields:
        FastAPI application.
    """
    yield create_app()


@pytest.fixture
def test_client(app: FastAPI) -> Iterator[TestClient]:
    """Fixture to construct a FastAPI test-client.

    Note:
        The app does not do lifecycle management.

    Yields:
        TestClient for the FastAPI application.
    """
    yield TestClient(app)


@pytest.fixture
def ad_connection() -> Iterator[MagicMock]:
    """Fixture to construct a mock ad_connection.

    Yields:
        A mock for ad_connection.
    """
    yield MagicMock()


def test_create_app(
    load_settings_overrides: dict[str, str],
) -> None:
    """Test that we can construct our FastAPI application."""

    with patch(
        "mo_ldap_import_export.main.configure_ad_connection", new_callable=MagicMock
    ):
        app = create_app()
    assert isinstance(app, FastAPI)


def test_create_fastramqpi(
    load_settings_overrides: dict[str, str], disable_metrics: None
) -> None:
    """Test that we can construct our FastRAMQPI system."""

    with patch(
        "mo_ldap_import_export.main.configure_ad_connection", new_callable=MagicMock
    ):
        fastramqpi = create_fastramqpi()
    assert isinstance(fastramqpi, FastRAMQPI)


async def test_open_ad_connection() -> None:
    """Test the open_ad_connection."""
    state = []

    @contextmanager
    def manager() -> Iterator[None]:
        state.append(1)
        yield
        state.append(2)

    ad_connection = manager()

    assert not state
    async with open_ad_connection(ad_connection):
        assert state == [1]
    assert state == [1, 2]


async def test_seed_dataloaders(fastramqpi: FastRAMQPI) -> None:
    """Test the seed_dataloaders asynccontextmanager."""

    fastramqpi.add_context(ad_connection=MagicMock)

    user_context = fastramqpi.get_context()["user_context"]
    assert user_context.get("dataloaders") is not None

    async with seed_dataloaders(fastramqpi):
        dataloaders = user_context.get("dataloaders")

    assert dataloaders is not None
    assert isinstance(dataloaders, Dataloaders)


def test_get_all_endpoint(test_client: TestClient, fastramqpi: FastRAMQPI) -> None:
    """Test the get-all endpoint on our app."""

    fastramqpi._context["user_context"]["dataloaders"]
    response = test_client.get("/all")

    assert response.status_code == 202
