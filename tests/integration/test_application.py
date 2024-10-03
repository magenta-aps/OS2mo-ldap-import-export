# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
"""Integration tests."""

import json
from collections.abc import Awaitable
from collections.abc import Callable
from datetime import datetime
from datetime import time
from unittest.mock import ANY
from unittest.mock import AsyncMock
from uuid import UUID
from uuid import uuid4

import pytest
from fastramqpi.context import Context
from fastramqpi.pytest_util import retry
from httpx import AsyncClient
from more_itertools import one

from mo_ldap_import_export.autogenerated_graphql_client import GraphQLClient
from mo_ldap_import_export.autogenerated_graphql_client.input_types import (
    EmployeeCreateInput,
)
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
from mo_ldap_import_export.utils import MO_TZ
from mo_ldap_import_export.utils import combine_dn_strings


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
    person_result = await graphql_client._testing_user_create(
        input=EmployeeCreateInput(given_name="John", surname="Hansen")
    )
    person_uuid = person_result.uuid

    await verify(person_uuid)

    sync_tool_mock.reset_mock()

    # Create an ITUser and verify that it ends up calling listen_to_changes_in_employees
    # In this case it does it by first emitting a employee_refresh event

    itsystem_result = await graphql_client._testing__itsystem_create(
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


@pytest.mark.integration_test
async def test_endpoint_default(test_client: AsyncClient) -> None:
    result = await test_client.get("/")
    assert result.status_code == 200
    assert result.json()["name"] == "ldap_ie"


@pytest.mark.integration_test
async def test_endpoint_dn2uuid_and_uuid2dn(
    test_client: AsyncClient,
    ldap_person: list[str],
) -> None:
    dn = combine_dn_strings(ldap_person)

    result = await test_client.get(f"/Inspect/dn2uuid/{dn}")
    assert result.status_code == 200
    entry_uuid = UUID(result.json())

    result = await test_client.get(f"/Inspect/uuid2dn/{entry_uuid}")
    assert result.status_code == 200
    read_dn = result.json()
    assert read_dn == dn


@pytest.mark.integration_test
async def test_endpoint_fetch_object(
    test_client: AsyncClient,
    ldap_person: list[str],
) -> None:
    dn = combine_dn_strings(ldap_person)

    expected = {
        "cn": ["Aage Bach Klarskov"],
        "dn": "uid=abk,ou=os2mo,o=magenta,dc=magenta,dc=dk",
        "employeeNumber": "2108613133",
        "givenName": ["Aage"],
        "mail": ["abk@ad.kolding.dk"],
        "objectClass": ["top", "person", "organizationalPerson", "inetOrgPerson"],
        "ou": ["os2mo"],
        "sn": ["Bach Klarskov"],
        "title": ["Skole underviser"],
        "uid": ["abk"],
        "userPassword": [None],
    }

    result = await test_client.get(f"/Inspect/dn/{dn}")
    assert result.status_code == 200
    assert result.json() == expected

    result = await test_client.get(f"/Inspect/dn2uuid/{dn}")
    assert result.status_code == 200
    entry_uuid = UUID(result.json())

    result = await test_client.get(f"/Inspect/uuid/{entry_uuid}")
    assert result.status_code == 200
    assert result.json() == expected


@pytest.mark.integration_test
async def test_endpoint_mo_uuid_to_ldap_dn(
    test_client: AsyncClient,
    graphql_client: GraphQLClient,
    ldap_person: list[str],
    mo_person: UUID,
) -> None:
    result = await test_client.get(f"/Inspect/mo/uuid2dn/{mo_person}")
    assert result.status_code == 200
    dn = one(result.json())
    assert dn == combine_dn_strings(ldap_person)


@pytest.mark.integration_test
async def test_endpoint_mo2ldap_templating(
    test_client: AsyncClient,
    graphql_client: GraphQLClient,
) -> None:
    given_name = "John"
    surname = "Hansen"
    cpr_number = "0101700000"
    # Create a person
    person_result = await graphql_client._testing_user_create(
        input=EmployeeCreateInput(
            given_name=given_name,
            surname=surname,
            cpr_number=cpr_number,
        )
    )
    person_uuid = person_result.uuid

    result = await test_client.get(f"/Inspect/mo2ldap/{person_uuid}")
    assert result.status_code == 200
    assert result.json() == {
        "Employee": [
            {
                "dn": "CN=Dry run,DC=example,DC=com",
                "employeeNumber": cpr_number,
                "givenName": given_name,
                "sn": surname,
                "title": str(person_uuid),
            },
            False,
        ]
    }


@pytest.mark.integration_test
@pytest.mark.usefixtures("test_client", "ldap_person")
async def test_create_ldap_person(
    test_client: AsyncClient,
    graphql_client: GraphQLClient,
    get_num_queued_messages: Callable[[], Awaitable[int]],
    get_num_published_messages: Callable[[], Awaitable[int]],
) -> None:
    given_name = "John"
    surname = "Hansen"
    cpr_number = "0101700000"
    # Create a person
    person_result = await graphql_client._testing_user_create(
        input=EmployeeCreateInput(
            given_name=given_name,
            surname=surname,
            cpr_number=cpr_number,
        )
    )
    person_uuid = person_result.uuid

    @retry()
    async def verify(person_uuid: UUID) -> None:
        num_messages = await get_num_published_messages()
        assert num_messages > 0

        num_messages = await get_num_queued_messages()
        assert num_messages == 0

        result = await test_client.get(f"/Inspect/mo/uuid2dn/{person_uuid}")
        assert result.status_code == 200
        dn = one(result.json())

        result = await test_client.get(f"/Inspect/dn/{dn}")
        assert result.status_code == 200
        assert result.json() == {
            "objectClass": ["inetOrgPerson"],
            "dn": dn,
            "cn": [given_name + " " + surname],
            "employeeNumber": cpr_number,
            "givenName": [given_name],
            "sn": [surname],
            "title": [str(person_uuid)],
        }

    await verify(person_uuid)


@pytest.mark.integration_test
@pytest.mark.envvar(
    {"IT_USER_TO_CHECK": "SynchronizeToLDAP", "LISTEN_TO_CHANGES_IN_LDAP": "False"}
)
@pytest.mark.usefixtures("ldap_person")
async def test_create_ldap_person_blocked_by_itsystem_check(
    test_client: AsyncClient,
    graphql_client: GraphQLClient,
    get_num_queued_messages: Callable[[], Awaitable[int]],
    get_num_published_messages: Callable[[], Awaitable[int]],
) -> None:
    given_name = "John"
    surname = "Hansen"
    cpr_number = "0101700000"

    # Create the SynchronizeToLDAP ITSystem
    await graphql_client._testing__itsystem_create(
        ITSystemCreateInput(
            user_key="SynchronizeToLDAP",
            name="SynchronizeToLDAP",
            validity=RAOpenValidityInput(),
        )
    )

    # Create a person
    person_result = await graphql_client._testing_user_create(
        input=EmployeeCreateInput(
            given_name=given_name,
            surname=surname,
            cpr_number=cpr_number,
        )
    )
    person_uuid = person_result.uuid

    @retry()
    async def verify(person_uuid: UUID) -> None:
        num_messages = await get_num_published_messages()
        assert num_messages > 0

        num_messages = await get_num_queued_messages()
        assert num_messages == 0

        # Check that the user has not been created
        result = await test_client.get(f"/Inspect/mo/uuid2dn/{person_uuid}")
        assert result.status_code == 200
        assert result.json() == []

    await verify(person_uuid)


@pytest.mark.integration_test
async def test_ldap2mo(test_client: AsyncClient) -> None:
    content = str(uuid4())
    headers = {"Content-Type": "text/plain"}
    result = await test_client.post("/ldap2mo/uuid", content=content, headers=headers)
    assert result.status_code == 451
    assert result.json() == {"detail": "LDAP UUID could not be found"}


@pytest.mark.integration_test
async def test_mo2ldap_address(test_client: AsyncClient) -> None:
    content = str(uuid4())
    headers = {"Content-Type": "text/plain"}
    result = await test_client.post(
        "/mo2ldap/address", content=content, headers=headers
    )
    assert result.status_code == 451
    assert result.json() == {"detail": "Unable to lookup address"}


@pytest.mark.integration_test
async def test_mo2ldap_engagement(test_client: AsyncClient) -> None:
    content = str(uuid4())
    headers = {"Content-Type": "text/plain"}
    result = await test_client.post(
        "/mo2ldap/engagement", content=content, headers=headers
    )
    assert result.status_code == 451
    assert result.json() == {"detail": "Unable to lookup engagement"}


@pytest.mark.integration_test
async def test_mo2ldap_ituser(test_client: AsyncClient) -> None:
    content = str(uuid4())
    headers = {"Content-Type": "text/plain"}
    result = await test_client.post("/mo2ldap/ituser", content=content, headers=headers)
    assert result.status_code == 451
    assert result.json() == {"detail": "Unable to lookup ITUser"}


@pytest.mark.integration_test
async def test_mo2ldap_person(test_client: AsyncClient) -> None:
    content = str(uuid4())
    headers = {"Content-Type": "text/plain"}
    result = await test_client.post("/mo2ldap/person", content=content, headers=headers)
    assert result.status_code == 500
    payload = result.json()
    assert payload.keys() == {"detail"}
    assert "Unable to lookup employee" in payload["detail"]


@pytest.mark.integration_test
async def test_mo2ldap_org_unit(test_client: AsyncClient) -> None:
    content = str(uuid4())
    headers = {"Content-Type": "text/plain"}
    result = await test_client.post(
        "/mo2ldap/org_unit", content=content, headers=headers
    )
    assert result.status_code == 200
    assert result.json() is None


@pytest.mark.integration_test
@pytest.mark.envvar(
    {"LISTEN_TO_CHANGES_IN_MO": "False", "LISTEN_TO_CHANGES_IN_LDAP": "False"}
)
@pytest.mark.parametrize(
    "expected", ([], pytest.param([], marks=pytest.mark.usefixtures("ldap_person")))
)
async def test_changed_since(test_client: AsyncClient, expected: list[str]) -> None:
    content = "ou=os2mo,o=magenta,dc=magenta,dc=dk"
    headers = {"Content-Type": "text/plain"}
    result = await test_client.request(
        "GET",
        "/ldap_event_generator/2000-01-01T00:00:00Z",
        content=content,
        headers=headers,
    )
    assert result.status_code == 200
    assert result.json() == expected


@pytest.mark.integration_test
@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_LDAP": "False",
        "LISTEN_TO_CHANGES_IN_MO": "False",
        "CONVERSION_MAPPING": json.dumps(
            {
                "ldap_to_mo": {
                    "Employee": {
                        "objectClass": "ramodels.mo.employee.Employee",
                        "_import_to_mo_": "false",
                        "uuid": "{{ employee_uuid or NONE }}",
                        "cpr_no": "{{ldap.employeeNumber|strip_non_digits or NONE}}",
                    },
                    "PublicEmailAddress": {
                        "objectClass": "ramodels.mo.details.address.Address",
                        "_import_to_mo_": "true",
                        "value": "{{ ldap.mail or NONE }}",
                        "address_type": "{{ dict(uuid=get_employee_address_type_uuid('EmailEmployee')) }}",
                        "person": "{{ dict(uuid=employee_uuid or NONE) }}",
                        "visibility": "{{ dict(uuid=get_visibility_uuid('Public')) }}",
                    },
                },
                "mo_to_ldap": {
                    "Employee": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "false",
                        "employeeNumber": "{{mo_employee.cpr_no}}",
                    },
                    "PublicEmailAddress": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "false",
                        "mail": "{{ mo_employee_address.value }}",
                    },
                },
                "username_generator": {
                    "objectClass": "UserNameGenerator",
                    "combinations_to_try": ["FFFX", "LLLX"],
                },
            }
        ),
    }
)
async def test_mismatched_json_key_and_address_type(
    test_client: AsyncClient,
    graphql_client: GraphQLClient,
    ldap_person: list[str],
    mo_person: UUID,
) -> None:
    """Test that json_key and address type does not need to match."""
    person_uuid = mo_person
    dn = combine_dn_strings(ldap_person)

    # Get UUID of the newly created LDAP user
    result = await test_client.get(f"/Inspect/dn2uuid/{dn}")
    assert result.status_code == 200
    ldap_user_uuid = UUID(result.json())

    # Fetch data in MO
    phone_employee_address_type_uuid = one(
        (
            await graphql_client.read_class_uuid_by_facet_and_class_user_key(
                "employee_address_type", "EmailEmployee"
            )
        ).objects
    ).uuid
    public_visibility_uuid = one(
        (
            await graphql_client.read_class_uuid_by_facet_and_class_user_key(
                "visibility", "Public"
            )
        ).objects
    ).uuid

    # Trigger synchronization, we expect the addresses to be updated with new values
    content = str(ldap_user_uuid)
    headers = {"Content-Type": "text/plain"}
    result = await test_client.post("/ldap2mo/uuid", content=content, headers=headers)
    assert result.status_code == 200

    # Lookup the newly synchronization address
    address = one(
        (
            await graphql_client.read_employee_addresses(
                employee_uuid=person_uuid,
                address_type_uuid=phone_employee_address_type_uuid,
            )
        ).objects
    )
    object_uuid = address.uuid
    assert address.dict() == {
        "uuid": object_uuid,
        "validities": [
            {
                "address_type": {
                    "user_key": "EmailEmployee",
                    "uuid": phone_employee_address_type_uuid,
                },
                "employee_uuid": person_uuid,
                "engagement_uuid": None,
                "org_unit_uuid": None,
                "person": [
                    {
                        "cpr_no": "2108613133",
                    }
                ],
                "uuid": object_uuid,
                "validity": {
                    "from_": datetime.combine(datetime.today(), time(tzinfo=MO_TZ)),
                    "to": None,
                },
                "value": "abk@ad.kolding.dk",
                "value2": None,
                "visibility_uuid": public_visibility_uuid,
            }
        ],
    }


@pytest.mark.integration_test
@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_LDAP": "False",
        "LISTEN_TO_CHANGES_IN_MO": "False",
        "CONVERSION_MAPPING": json.dumps(
            {
                "ldap_to_mo": {
                    "Employee": {
                        "objectClass": "ramodels.mo.employee.Employee",
                        "_import_to_mo_": "false",
                        "uuid": "{{ employee_uuid or NONE }}",
                        "cpr_no": "{{ldap.employeeNumber|strip_non_digits or NONE}}",
                    },
                    "EntryUUID": {
                        "objectClass": "ramodels.mo.details.it_system.ITUser",
                        "_import_to_mo_": "true",
                        "user_key": "{{ ldap.entryUUID or NONE }}",
                        "itsystem": "{{ dict(uuid=get_it_system_uuid('ADUUID')) }}",
                        "person": "{{ dict(uuid=employee_uuid or NONE) }}",
                    },
                },
                "mo_to_ldap": {
                    "Employee": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "false",
                        "employeeNumber": "{{mo_employee.cpr_no}}",
                    },
                    "EntryUUID": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "false",
                        "entryUUID": "{{ mo_employee_it_user.user_key }}",
                    },
                },
                "username_generator": {
                    "objectClass": "UserNameGenerator",
                    "combinations_to_try": ["FFFX", "LLLX"],
                },
            }
        ),
    }
)
async def test_mismatched_json_key_and_itsystem(
    test_client: AsyncClient,
    graphql_client: GraphQLClient,
    ldap_person: list[str],
    mo_person: UUID,
) -> None:
    """Test that json_key and itsystem does not need to match."""
    person_uuid = mo_person
    dn = combine_dn_strings(ldap_person)

    # Get UUID of the newly created LDAP user
    result = await test_client.get(f"/Inspect/dn2uuid/{dn}")
    assert result.status_code == 200
    ldap_user_uuid = UUID(result.json())

    # Fetch data in MO
    ldap_uuid_itsystem_uuid = one(
        (await graphql_client.read_itsystem_uuid("ADUUID")).objects
    ).uuid

    # Trigger synchronization, we expect the addresses to be updated with new values
    content = str(ldap_user_uuid)
    headers = {"Content-Type": "text/plain"}
    result = await test_client.post("/ldap2mo/uuid", content=content, headers=headers)
    assert result.status_code == 200

    # Lookup the newly synchronization address
    ituser_uuids = [
        x.uuid
        for x in (
            await graphql_client.read_ituser_by_employee_and_itsystem_uuid(
                employee_uuid=person_uuid, itsystem_uuid=ldap_uuid_itsystem_uuid
            )
        ).objects
    ]
    ituser = one(
        (
            await graphql_client.read_itusers(
                uuids=ituser_uuids,
            )
        ).objects
    )

    assert ituser.dict() == {
        "validities": [
            {
                "employee_uuid": person_uuid,
                "engagement_uuid": None,
                "itsystem_uuid": ldap_uuid_itsystem_uuid,
                "user_key": str(ldap_user_uuid),
                "validity": {
                    "from_": datetime.combine(datetime.today(), time(tzinfo=MO_TZ)),
                    "to": None,
                },
            }
        ],
    }


@pytest.mark.integration_test
@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_LDAP": "False",
        "LISTEN_TO_CHANGES_IN_MO": "False",
        "CONVERSION_MAPPING": json.dumps(
            {
                "ldap_to_mo": {
                    "Employee": {
                        "objectClass": "ramodels.mo.employee.Employee",
                        "_import_to_mo_": "false",
                        "uuid": "{{ employee_uuid or NONE }}",
                        "cpr_no": "{{ldap.employeeNumber|strip_non_digits or NONE}}",
                    },
                    "DefaultValidity": {
                        "objectClass": "ramodels.mo.details.it_system.ITUser",
                        "_import_to_mo_": "true",
                        "user_key": "{{ ldap.entryUUID or NONE }}",
                        "itsystem": "{{ dict(uuid=get_it_system_uuid('ADUUID')) }}",
                        "person": "{{ dict(uuid=employee_uuid or NONE) }}",
                    },
                    "SetValidity": {
                        "objectClass": "ramodels.mo.details.it_system.ITUser",
                        "_import_to_mo_": "true",
                        "user_key": "{{ ldap.mail or NONE }}",
                        "itsystem": "{{ dict(uuid=get_it_system_uuid('ADUUID')) }}",
                        "person": "{{ dict(uuid=employee_uuid or NONE) }}",
                        "validity": "{{ dict(from_date=now()|mo_datestring) }}",
                    },
                },
                "mo_to_ldap": {
                    "Employee": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "false",
                        "employeeNumber": "{{mo_employee.cpr_no}}",
                    },
                    "DefaultValidity": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "false",
                        "entryUUID": "{{ mo_employee_it_user.user_key }}",
                    },
                    "SetValidity": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "false",
                        "mail": "{{ mo_employee_it_user.user_key }}",
                    },
                },
                "username_generator": {
                    "objectClass": "UserNameGenerator",
                    "combinations_to_try": ["FFFX", "LLLX"],
                },
            }
        ),
    }
)
async def test_default_validity(
    test_client: AsyncClient,
    graphql_client: GraphQLClient,
    ldap_person: list[str],
    mo_person: UUID,
) -> None:
    """Test that json_key and itsystem does not need to match."""
    person_uuid = mo_person
    dn = combine_dn_strings(ldap_person)

    # Get UUID of the newly created LDAP user
    result = await test_client.get(f"/Inspect/dn2uuid/{dn}")
    assert result.status_code == 200
    ldap_user_uuid = UUID(result.json())

    # Fetch data in MO
    ldap_uuid_itsystem_uuid = one(
        (await graphql_client.read_itsystem_uuid("ADUUID")).objects
    ).uuid

    # Trigger synchronization, we expect the addresses to be updated with new values
    content = str(ldap_user_uuid)
    headers = {"Content-Type": "text/plain"}
    result = await test_client.post("/ldap2mo/uuid", content=content, headers=headers)
    assert result.status_code == 200

    # Lookup the newly synchronization address
    ituser_uuids = [
        x.uuid
        for x in (
            await graphql_client.read_ituser_by_employee_and_itsystem_uuid(
                employee_uuid=person_uuid, itsystem_uuid=ldap_uuid_itsystem_uuid
            )
        ).objects
    ]
    assert len(ituser_uuids) == 2
    itusers = [
        ituser.dict()
        for ituser in (
            await graphql_client.read_itusers(
                uuids=ituser_uuids,
            )
        ).objects
    ]
    assert len(itusers) == 2

    assert itusers == [
        {
            "validities": [
                {
                    "employee_uuid": person_uuid,
                    "engagement_uuid": None,
                    "itsystem_uuid": ldap_uuid_itsystem_uuid,
                    "user_key": ANY,
                    "validity": {
                        "from_": datetime.combine(datetime.today(), time(tzinfo=MO_TZ)),
                        "to": None,
                    },
                }
            ]
        }
        for _ in range(2)
    ]
