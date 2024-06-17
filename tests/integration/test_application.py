# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
"""Integration tests."""
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastramqpi.context import Context
from fastramqpi.pytest_util import retry
from httpx import AsyncClient
from ldap3 import Connection

from mo_ldap_import_export.autogenerated_graphql_client import GraphQLClient
from mo_ldap_import_export.autogenerated_graphql_client.input_types import (
    ITSystemCreateInput,
)
from mo_ldap_import_export.autogenerated_graphql_client.input_types import (
    ITUserCreateInput,
)
from mo_ldap_import_export.autogenerated_graphql_client.input_types import (
    RAOpenValidityInput,
)
from mo_ldap_import_export.autogenerated_graphql_client.input_types import (
    RAValidityInput,
)
from mo_ldap_import_export.ldap import ldap_add


@pytest.mark.integration_test
@pytest.mark.usefixtures("test_client")
async def test_process_person(
    graphql_client: GraphQLClient,
    context: Context,
) -> None:
    sync_tool_mock = AsyncMock()
    context["user_context"]["sync_tool"] = sync_tool_mock

    @retry()
    async def verify(person_uuid) -> None:
        sync_tool_mock.listen_to_changes_in_employees.assert_called_with(person_uuid)

    # Create a person and verify that it ends up calling listen_to_changes_in_employees
    person_result = await graphql_client._testing_user_create("John", "Hansen")
    person_uuid = person_result.uuid

    await verify(person_uuid)

    sync_tool_mock.reset_mock()

    # Create an ITUser and verify that it ends up calling listen_to_changes_in_employees
    # In this case it does it by first emitting a employee_refresh event

    itsystem_result = await graphql_client.itsystem_create(
        ITSystemCreateInput(
            user_key="test", name="test", validity=RAOpenValidityInput()
        )
    )
    itsystem_uuid = itsystem_result.uuid

    await graphql_client._testing_ituser_create(
        ITUserCreateInput(
            person=person_uuid,
            user_key="test",
            itsystem=itsystem_uuid,
            validity=RAValidityInput(from_="1970-01-01T00:00:00"),
        )
    )

    await verify(person_uuid)


@pytest.fixture
async def ldap_dummy_data(ldap_connection: Connection) -> str:
    suffix = ",dc=magenta,dc=dk"
    await ldap_add(
        ldap_connection,
        "o=magenta" + suffix,
        object_class=["top", "organization"],
        attributes={"objectClass": ["top", "organization"], "o": "magenta"},
    )
    await ldap_add(
        ldap_connection,
        "ou=os2mo,o=magenta" + suffix,
        object_class=["top", "organizationalUnit"],
        attributes={"objectClass": ["top", "organizationalUnit"], "ou": "os2mo"},
    )
    dn = "uid=abk,ou=os2mo,o=magenta" + suffix
    await ldap_add(
        ldap_connection,
        dn,
        object_class=["top", "person", "organizationalPerson", "inetOrgPerson"],
        attributes={
            "objectClass": ["top", "person", "organizationalPerson", "inetOrgPerson"],
            "uid": "abk",
            "cn": "Aage Bach Klarskov",
            "givenName": "Aage",
            "sn": "Bach Klarskov",
            "ou": "os2mo",
            "mail": "abk@ad.kolding.dk",
            "userPassword": "{SSHA}j3lBh1Seqe4rqF1+NuWmjhvtAni1JC5A",
            "employeeNumber": "2108613133",
            "title": "Skole underviser",
        },
    )
    return dn


@pytest.mark.integration_test
async def test_endpoint_default(test_client: AsyncClient) -> None:
    result = await test_client.get("/")
    assert result.status_code == 200
    assert result.json()["name"] == "ldap_ie"


@pytest.mark.integration_test
async def test_endpoint_dn2uuid_and_uuid2dn(
    test_client: AsyncClient,
    ldap_dummy_data: str,
) -> None:
    dn = ldap_dummy_data
    print("url:", f"/LDAP/dn2uuid/{dn}")

    result = await test_client.get(f"/LDAP/dn2uuid/{dn}")
    assert result.status_code == 200
    entry_uuid = UUID(result.json())

    result = await test_client.get(f"/LDAP/uuid2dn/{entry_uuid}")
    assert result.status_code == 200
    read_dn = result.json()
    assert read_dn == dn
