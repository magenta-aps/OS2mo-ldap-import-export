# SPDX-FileCopyrightText: Magenta ApS <https://magenta.dk>
# SPDX-License-Identifier: MPL-2.0
from datetime import datetime
from unittest.mock import ANY
from uuid import UUID
from uuid import uuid4

import pytest
from fastramqpi.context import Context
from structlog.testing import capture_logs

from mo_ldap_import_export.autogenerated_graphql_client.input_types import (
    ITUserCreateInput,
)
from mo_ldap_import_export.depends import GraphQLClient
from mo_ldap_import_export.environments import load_it_user
from mo_ldap_import_export.moapi import MOAPI
from mo_ldap_import_export.utils import MO_TZ


@pytest.mark.integration_test
@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_MO": "False",
        "LISTEN_TO_CHANGES_IN_LDAP": "False",
    }
)
@pytest.mark.usefixtures("test_client")
async def test_load_it_user(
    graphql_client: GraphQLClient,
    context: Context,
    mo_api: MOAPI,
    mo_person: UUID,
) -> None:
    title = "create"
    it_system_uuid = UUID(await mo_api.get_it_system_uuid("ADtitle"))
    await graphql_client.ituser_create(
        input=ITUserCreateInput(
            user_key=title,
            itsystem=it_system_uuid,
            person=mo_person,
            validity={"from": "2001-02-03T04:05:06Z"},
        )
    )

    dataloader = context["user_context"]["dataloader"]
    result = await load_it_user(dataloader.moapi, mo_person, "ADtitle")
    assert result is not None
    assert result.dict(exclude_none=True) == {
        "itsystem": it_system_uuid,
        "person": mo_person,
        "user_key": title,
        "uuid": ANY,
        "validity": {"start": datetime(2001, 2, 3, 0, 0, tzinfo=MO_TZ)},
    }


@pytest.mark.integration_test
@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_MO": "False",
        "LISTEN_TO_CHANGES_IN_LDAP": "False",
    }
)
@pytest.mark.usefixtures("test_client")
async def test_load_it_user_deleted(
    graphql_client: GraphQLClient,
    context: Context,
    mo_api: MOAPI,
    mo_person: UUID,
) -> None:
    it_system_uuid = UUID(await mo_api.get_it_system_uuid("ADtitle"))
    await graphql_client.ituser_create(
        input=ITUserCreateInput(
            user_key="terminated_ituser",
            itsystem=it_system_uuid,
            person=mo_person,
            validity={"from": "2001-02-03T04:05:06Z", "to": "2002-03-04T05:06:07Z"},
        )
    )

    dataloader = context["user_context"]["dataloader"]
    with capture_logs() as cap_logs:
        result = await load_it_user(dataloader.moapi, mo_person, "ADtitle")
    assert result is None

    events = [m["event"] for m in cap_logs]
    assert events == [
        "Returning delete=True because to_date <= current_date",
        "IT-user is terminated",
    ]


@pytest.mark.integration_test
@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_MO": "False",
        "LISTEN_TO_CHANGES_IN_LDAP": "False",
    }
)
@pytest.mark.usefixtures("test_client")
async def test_load_it_user_multiple_matches(
    graphql_client: GraphQLClient,
    context: Context,
    mo_api: MOAPI,
    mo_person: UUID,
) -> None:
    it_system_uuid = UUID(await mo_api.get_it_system_uuid("ADtitle"))
    await graphql_client.ituser_create(
        input=ITUserCreateInput(
            user_key="ituser1",
            itsystem=it_system_uuid,
            person=mo_person,
            validity={"from": "2001-02-03T04:05:06Z"},
        )
    )
    await graphql_client.ituser_create(
        input=ITUserCreateInput(
            user_key="ituser2",
            itsystem=it_system_uuid,
            person=mo_person,
            validity={"from": "2001-02-03T04:05:06Z"},
        )
    )

    dataloader = context["user_context"]["dataloader"]
    with pytest.raises(ValueError) as exc_info:
        await load_it_user(dataloader.moapi, mo_person, "ADtitle")
    assert "Expected exactly one item in iterable" in str(exc_info.value)


@pytest.mark.integration_test
@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_MO": "False",
        "LISTEN_TO_CHANGES_IN_LDAP": "False",
    }
)
@pytest.mark.usefixtures("test_client")
async def test_load_it_user_invalid_employee(context: Context) -> None:
    dataloader = context["user_context"]["dataloader"]
    employee_uuid = uuid4()
    with capture_logs() as cap_logs:
        result = await load_it_user(dataloader.moapi, employee_uuid, "ADtitle")
    assert result is None

    events = [m["event"] for m in cap_logs]
    assert events == ["Could not find it-user"]


@pytest.mark.integration_test
@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_MO": "False",
        "LISTEN_TO_CHANGES_IN_LDAP": "False",
    }
)
@pytest.mark.usefixtures("test_client")
async def test_load_it_user_invalid_itsystem(context: Context, mo_person: UUID) -> None:
    dataloader = context["user_context"]["dataloader"]
    with capture_logs() as cap_logs:
        result = await load_it_user(
            dataloader.moapi, mo_person, "non_existing_it_system"
        )
    assert result is None

    events = [m["event"] for m in cap_logs]
    assert events == ["Could not find it-user"]


@pytest.mark.integration_test
@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_MO": "False",
        "LISTEN_TO_CHANGES_IN_LDAP": "False",
    }
)
@pytest.mark.usefixtures("test_client")
async def test_load_it_user_no_it_user(context: Context, mo_person: UUID) -> None:
    dataloader = context["user_context"]["dataloader"]
    with capture_logs() as cap_logs:
        result = await load_it_user(dataloader.moapi, mo_person, "ADtitle")
    assert result is None

    events = [m["event"] for m in cap_logs]
    assert events == ["Could not find it-user"]


@pytest.mark.integration_test
@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_MO": "False",
        "LISTEN_TO_CHANGES_IN_LDAP": "False",
    }
)
@pytest.mark.usefixtures("test_client")
async def test_load_itusers_multiple_disjoint_matches(
    graphql_client: GraphQLClient,
    context: Context,
    mo_api: MOAPI,
    mo_person: UUID,
) -> None:
    it_system_uuid = UUID(await mo_api.get_it_system_uuid("ADtitle"))

    await graphql_client.ituser_create(
        input=ITUserCreateInput(
            user_key="User1",
            itsystem=it_system_uuid,
            person=mo_person,
            validity={"from": "2001-02-03T04:05:06Z", "to": "2002-03-04T05:06:07Z"},
        )
    )
    await graphql_client.ituser_create(
        input=ITUserCreateInput(
            user_key="User2",
            itsystem=it_system_uuid,
            person=mo_person,
            validity={"from": "2003-04-05T06:07:08Z"},
        )
    )

    dataloader = context["user_context"]["dataloader"]
    result = await load_it_user(dataloader.moapi, mo_person, "ADtitle")
    assert result is not None
    assert result.user_key == "User2"
