# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
import json
from unittest.mock import ANY
from uuid import UUID

import pytest
from fastramqpi.pytest_util import retry
from httpx import AsyncClient
from ldap3 import Connection
from more_itertools import one

from mo_ldap_import_export.autogenerated_graphql_client import EmployeeFilter
from mo_ldap_import_export.autogenerated_graphql_client import GraphQLClient
from mo_ldap_import_export.autogenerated_graphql_client import ITUserCreateInput
from mo_ldap_import_export.autogenerated_graphql_client import ITUserFilter
from mo_ldap_import_export.autogenerated_graphql_client import ITUserUpdateInput
from mo_ldap_import_export.ldap import ldap_add
from mo_ldap_import_export.ldap import ldap_modify
from mo_ldap_import_export.ldap import ldap_search
from mo_ldap_import_export.moapi import MOAPI
from mo_ldap_import_export.utils import combine_dn_strings
from mo_ldap_import_export.utils import mo_today


@pytest.mark.integration_test
@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_MO": "False",
        "LISTEN_TO_CHANGES_IN_LDAP": "True",
        "CONVERSION_MAPPING": json.dumps(
            {
                "ldap_to_mo": {
                    "Employee": {
                        "objectClass": "ramodels.mo.employee.Employee",
                        "_import_to_mo_": "false",
                        "uuid": "{{ employee_uuid or NONE }}",  # TODO: why is this required?
                        "cpr_no": "{{ldap.employeeNumber}}",
                    },
                    "ADtitle": {
                        "objectClass": "ramodels.mo.details.it_system.ITUser",
                        "_import_to_mo_": "true",
                        "_mapper_": "{{ obj.itsystem }}",
                        # carLicense is arbitrarily chosen as an enabled/disabled marker
                        "_terminate_": "{{ now()|mo_datestring if ldap.carLicense == 'EXPIRED' else NONE}}",
                        "user_key": "{{ ldap.title }}",
                        "person": "{{ dict(uuid=employee_uuid ) }}",
                        "itsystem": "{{ dict(uuid=get_it_system_uuid('ADtitle')) }}",
                    },
                },
                # TODO: why is this required?
                "mo_to_ldap": {
                    "Employee": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "false",
                        "employeeNumber": "{{mo_employee.cpr_no}}",
                    },
                    "ADtitle": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "false",
                        "title": "{{ mo_employee_it_user.user_key }}",
                        "employeeNumber": "{{ mo_employee.cpr_no }}",
                        "carLicense": "unused but required",
                    },
                },
                # TODO: why is this required?
                "username_generator": {
                    "objectClass": "UserNameGenerator",
                    "combinations_to_try": ["FFFX", "LLLX"],
                },
            }
        ),
    }
)
async def test_to_mo(
    test_client: AsyncClient,
    graphql_client: GraphQLClient,
    mo_person: UUID,
    ldap_connection: Connection,
    ldap_org: list[str],
) -> None:
    @retry()
    async def assert_it_user(expected: dict) -> None:
        it_users = await graphql_client._testing__ituser_read(
            filter=ITUserFilter(
                employee=EmployeeFilter(uuids=[mo_person]),
            ),
        )
        it_user = one(it_users.objects)
        validities = one(it_user.validities)
        assert validities.dict() == expected

    person_dn = combine_dn_strings(["uid=abk"] + ldap_org)

    # LDAP: Create
    title = "create"
    await ldap_add(
        ldap_connection,
        dn=person_dn,
        object_class=["top", "person", "organizationalPerson", "inetOrgPerson"],
        attributes={
            "objectClass": ["top", "person", "organizationalPerson", "inetOrgPerson"],
            "ou": "os2mo",
            "cn": "Aage Bach Klarskov",
            "sn": "Bach Klarskov",
            "employeeNumber": "2108613133",
            "title": title,
            "carLicense": "ACTIVE",
        },
    )
    mo_it_user = {
        "uuid": ANY,
        "user_key": title,
        "itsystem": {"user_key": "ADtitle"},
        "person": [{"uuid": mo_person}],
        "validity": {"from_": mo_today(), "to": None},
    }
    await assert_it_user(mo_it_user)

    # LDAP: Edit
    title = "edit"
    await ldap_modify(
        ldap_connection,
        dn=person_dn,
        changes={
            "title": [("MODIFY_REPLACE", title)],
        },
    )
    mo_it_user = {
        **mo_it_user,
        "user_key": title,
    }
    await assert_it_user(mo_it_user)

    # LDAP: Terminate
    await ldap_modify(
        ldap_connection,
        dn=person_dn,
        changes={
            "carLicense": [("MODIFY_REPLACE", "EXPIRED")],
        },
    )
    mo_it_user = {
        **mo_it_user,
        "validity": {"from_": mo_today(), "to": mo_today()},
    }
    await assert_it_user(mo_it_user)


@pytest.mark.integration_test
@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_MO": "True",
        "LISTEN_TO_CHANGES_IN_LDAP": "False",
        "CONVERSION_MAPPING": json.dumps(
            {
                # TODO: why is this required?
                "ldap_to_mo": {
                    "Employee": {
                        "objectClass": "ramodels.mo.employee.Employee",
                        "_import_to_mo_": "false",
                        "uuid": "{{ employee_uuid or NONE }}",
                        "cpr_no": "{{ldap.employeeNumber}}",
                    },
                    "ADtitle": {
                        "objectClass": "ramodels.mo.details.it_system.ITUser",
                        "_import_to_mo_": "false",
                        "_mapper_": "{{ obj.itsystem }}",
                        "user_key": "{{ ldap.title }}",
                        "person": "{{ dict(uuid=employee_uuid ) }}",
                        "itsystem": "{{ dict(uuid=get_it_system_uuid('ADtitle')) }}",
                    },
                },
                "mo_to_ldap": {
                    "Employee": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "false",
                        "employeeNumber": "{{mo_employee.cpr_no}}",
                    },
                    "ADtitle": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "true",
                        "title": "{{ mo_employee_it_user.user_key }}",
                        "employeeNumber": "{{ mo_employee.cpr_no }}",
                        "carLicense": "unused but required",
                    },
                },
                # TODO: why is this required?
                "username_generator": {
                    "objectClass": "UserNameGenerator",
                    "combinations_to_try": ["FFFX", "LLLX"],
                },
            }
        ),
    }
)
async def test_to_ldap(
    test_client: AsyncClient,
    graphql_client: GraphQLClient,
    mo_api: MOAPI,
    mo_person: UUID,
    ldap_connection: Connection,
    ldap_org: list[str],
) -> None:
    cpr = "2108613133"

    @retry()
    async def assert_it_user(expected: list[str]) -> None:
        response, _ = await ldap_search(
            ldap_connection,
            search_base=combine_dn_strings(ldap_org),
            search_filter=f"(employeeNumber={cpr})",
            attributes=["distinguishedName", "title"],
        )
        assert one(response)["attributes"]["title"] == expected

    # LDAP: Init user
    person_dn = combine_dn_strings(["uid=abk"] + ldap_org)
    await ldap_add(
        ldap_connection,
        dn=person_dn,
        object_class=["top", "person", "organizationalPerson", "inetOrgPerson"],
        attributes={
            "objectClass": ["top", "person", "organizationalPerson", "inetOrgPerson"],
            "ou": "os2mo",
            "cn": "Aage Bach Klarskov",
            "sn": "Bach Klarskov",
            "employeeNumber": cpr,
        },
    )
    await assert_it_user([])

    # MO: Create
    it_system_uuid = UUID(await mo_api.get_it_system_uuid("ADtitle"))
    title = "create"
    mo_it_user = await graphql_client._testing_ituser_create(
        input=ITUserCreateInput(
            user_key=title,
            itsystem=it_system_uuid,
            person=mo_person,
            validity={"from": "2001-02-03T04:05:06Z"},
        )
    )
    await assert_it_user([title])

    # MO: Edit
    title = "update"
    await graphql_client._testing_ituser_update(
        input=ITUserUpdateInput(
            uuid=mo_it_user.uuid,
            user_key=title,
            validity={"from": "2011-12-13T14:15:16Z"},
            # TODO: why is this required?
            itsystem=it_system_uuid,
            person=mo_person,
        )
    )
    await assert_it_user([title])

    # MO: Terminate
    await graphql_client._testing_ituser_terminate(
        uuid=mo_it_user.uuid,
        to=mo_today(),
    )
    await assert_it_user([])
