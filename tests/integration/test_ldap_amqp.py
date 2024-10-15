# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0

from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastramqpi.depends import from_user_context
from httpx import AsyncClient
from structlog.testing import capture_logs


@pytest.mark.integration_test
async def test_process_uuid_missing_uuid(test_client: AsyncClient) -> None:
    """Test that process_uuid fails as expected."""
    with capture_logs() as cap_logs:
        result = await test_client.post(
            "/ldap2mo/uuid",
            headers={"Content-Type": "text/plain"},
            content=str(UUID("00000000-00000000-00000000-00000000")),
        )

    assert result.status_code == 451
    assert "LDAP UUID could not be found" in str(cap_logs)


@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_MO": "False",
        "LISTEN_TO_CHANGES_IN_LDAP": "False",
    }
)
@pytest.mark.integration_test
async def test_process_uuid_bad_sync(
    app: FastAPI,
    test_client: AsyncClient,
    ldap_person_uuid: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that process_uuid fails as expected."""
    sync_tool = AsyncMock()
    sync_tool.import_single_user.side_effect = ValueError("BOOM")
    app.dependency_overrides[from_user_context("sync_tool")] = lambda: sync_tool

    monkeypatch.setattr("asyncio.sleep", AsyncMock())

    with capture_logs() as cap_logs:
        result = await test_client.post(
            "/ldap2mo/uuid",
            headers={"Content-Type": "text/plain"},
            content=str(ldap_person_uuid),
        )

    assert result.status_code == 500

    assert {
        "event": "Registered change for LDAP object(s)",
        "uuids": [ldap_person_uuid],
        "log_level": "info",
    } in cap_logs