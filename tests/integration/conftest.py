# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
from collections.abc import Awaitable
from collections.abc import Callable
from uuid import UUID

import pytest
from ldap3 import Connection
from more_itertools import one

from mo_ldap_import_export.autogenerated_graphql_client import EmployeeCreateInput
from mo_ldap_import_export.autogenerated_graphql_client import GraphQLClient
from mo_ldap_import_export.autogenerated_graphql_client import (
    OrganisationUnitCreateInput,
)
from mo_ldap_import_export.ldap import ldap_add
from mo_ldap_import_export.ldapapi import LDAPAPI
from mo_ldap_import_export.utils import combine_dn_strings


@pytest.fixture
def ldap_suffix() -> list[str]:
    return ["dc=magenta", "dc=dk"]


@pytest.fixture
async def ldap_org(ldap_connection: Connection, ldap_suffix: list[str]) -> list[str]:
    o_dn = ["o=magenta"] + ldap_suffix
    await ldap_add(
        ldap_connection,
        combine_dn_strings(o_dn),
        object_class=["top", "organization"],
        attributes={"objectClass": ["top", "organization"], "o": "magenta"},
    )
    ou_dn = ["ou=os2mo"] + o_dn
    await ldap_add(
        ldap_connection,
        combine_dn_strings(ou_dn),
        object_class=["top", "organizationalUnit"],
        attributes={"objectClass": ["top", "organizationalUnit"], "ou": "os2mo"},
    )
    return ou_dn


AddLdapPerson = Callable[[str, str], Awaitable[list[str]]]


@pytest.fixture
async def add_ldap_person(
    ldap_connection: Connection, ldap_org: list[str]
) -> AddLdapPerson:
    async def adder(identifier: str, cpr_number: str) -> list[str]:
        person_dn = ["uid=" + identifier] + ldap_org
        await ldap_add(
            ldap_connection,
            combine_dn_strings(person_dn),
            object_class=["top", "person", "organizationalPerson", "inetOrgPerson"],
            attributes={
                "objectClass": [
                    "top",
                    "person",
                    "organizationalPerson",
                    "inetOrgPerson",
                ],
                "uid": identifier,
                "cn": "cn",
                "givenName": "givenName",
                "sn": "sn",
                "ou": "os2mo",
                "mail": identifier + "@ad.kolding.dk",
                "userPassword": "{SSHA}j3lBh1Seqe4rqF1+NuWmjhvtAni1JC5A",
                "employeeNumber": cpr_number,
                "title": "title",
            },
        )
        return person_dn

    return adder


@pytest.fixture
async def ldap_person(ldap_connection: Connection, ldap_org: list[str]) -> list[str]:
    person_dn = ["uid=abk"] + ldap_org
    await ldap_add(
        ldap_connection,
        combine_dn_strings(person_dn),
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
    return person_dn


@pytest.fixture
async def ldap_person_uuid(ldap_person: list[str], ldap_api: LDAPAPI) -> UUID:
    dn = combine_dn_strings(ldap_person)
    return await ldap_api.get_ldap_unique_ldap_uuid(dn)


@pytest.fixture
async def mo_person(graphql_client: GraphQLClient) -> UUID:
    r = await graphql_client.user_create(
        input=EmployeeCreateInput(
            given_name="Aage",
            surname="Bach Klarskov",
            cpr_number="2108613133",
        )
    )
    return r.uuid


@pytest.fixture
async def mo_org_unit(graphql_client: GraphQLClient) -> UUID:
    afdeling = one(
        (
            await graphql_client.read_class_uuid_by_facet_and_class_user_key(
                "org_unit_type", "Afdeling"
            )
        ).objects
    )
    r = await graphql_client._testing_org_unit_create(
        input=OrganisationUnitCreateInput(
            user_key="os2mo",
            name="os2mo",
            parent=None,
            org_unit_type=afdeling.uuid,
            validity={"from": "1960-01-01T00:00:00Z"},
        )
    )
    return r.uuid


@pytest.fixture
async def ansat(graphql_client: GraphQLClient) -> UUID:
    return one(
        (
            await graphql_client.read_class_uuid_by_facet_and_class_user_key(
                "engagement_type", "Ansat"
            )
        ).objects
    ).uuid


@pytest.fixture
async def jurist(graphql_client: GraphQLClient) -> UUID:
    return one(
        (
            await graphql_client.read_class_uuid_by_facet_and_class_user_key(
                "engagement_job_function", "Jurist"
            )
        ).objects
    ).uuid


@pytest.fixture
async def primary(graphql_client: GraphQLClient) -> UUID:
    return one(
        (
            await graphql_client.read_class_uuid_by_facet_and_class_user_key(
                "primary_type", "primary"
            )
        ).objects
    ).uuid


@pytest.fixture
async def non_primary(graphql_client: GraphQLClient) -> UUID:
    return one(
        (
            await graphql_client.read_class_uuid_by_facet_and_class_user_key(
                "primary_type", "non-primary"
            )
        ).objects
    ).uuid


@pytest.fixture
async def email_employee(graphql_client: GraphQLClient) -> UUID:
    return one(
        (
            await graphql_client.read_class_uuid_by_facet_and_class_user_key(
                "employee_address_type", "EmailEmployee"
            )
        ).objects
    ).uuid


@pytest.fixture
async def email_unit(graphql_client: GraphQLClient) -> UUID:
    return one(
        (
            await graphql_client.read_class_uuid_by_facet_and_class_user_key(
                "org_unit_address_type", "EmailUnit"
            )
        ).objects
    ).uuid


@pytest.fixture
async def public(graphql_client: GraphQLClient) -> UUID:
    return one(
        (
            await graphql_client.read_class_uuid_by_facet_and_class_user_key(
                "visibility", "Public"
            )
        ).objects
    ).uuid
