# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
import json
from typing import Any
from unittest.mock import ANY
from uuid import UUID

import pytest
from fastramqpi.pytest_util import retry
from httpx import AsyncClient
from ldap3 import Connection
from more_itertools import one

from mo_ldap_import_export.autogenerated_graphql_client import EmployeeFilter
from mo_ldap_import_export.autogenerated_graphql_client import EngagementCreateInput
from mo_ldap_import_export.autogenerated_graphql_client import EngagementFilter
from mo_ldap_import_export.autogenerated_graphql_client import EngagementTerminateInput
from mo_ldap_import_export.autogenerated_graphql_client import EngagementUpdateInput
from mo_ldap_import_export.autogenerated_graphql_client import GraphQLClient
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
                        "_ldap_attributes_": [],
                        "uuid": "{{ employee_uuid or '' }}",  # TODO: why is this required?
                    },
                    "Engagement": {
                        "objectClass": "ramodels.mo.details.engagement.Engagement",
                        "_import_to_mo_": "true",
                        "_ldap_attributes_": [
                            "carLicense",
                            "title",
                            "departmentNumber",
                        ],
                        "_mapper_": "{{ obj.org_unit }}",
                        # carLicense is arbitrarily chosen as an enabled/disabled marker
                        "_terminate_": "{{ now()|mo_datestring if ldap.carLicense == 'EXPIRED' else '' }}",
                        "user_key": "{{ ldap.title }}",
                        "person": "{{ dict(uuid=employee_uuid ) }}",
                        "org_unit": "{{ dict(uuid=ldap.departmentNumber ) }}",
                        "engagement_type": "{{ dict(uuid=get_engagement_type_uuid('Ansat')) }}",
                        "job_function": "{{ dict(uuid=get_job_function_uuid('Jurist')) }}",
                        "primary": "{{ dict(uuid=get_primary_type_uuid('primary')) }}",
                        "extension_1": "{{ ldap.title }}",
                    },
                },
                # TODO: why is this required?
                "mo_to_ldap": {
                    "Employee": {
                        "_export_to_ldap_": "false",
                    }
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
    mo_org_unit: UUID,
    ldap_connection: Connection,
    ldap_org: list[str],
) -> None:
    @retry()
    async def assert_engagement(expected: dict) -> None:
        engagements = await graphql_client._testing__engagement_read(
            filter=EngagementFilter(
                employee=EmployeeFilter(uuids=[mo_person]),
            ),
        )
        engagement = one(engagements.objects)
        validities = one(engagement.validities)
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
            "carLicense": "ACTIVE",
            "title": title,
            "departmentNumber": str(mo_org_unit),
        },
    )
    mo_engagement = {
        "uuid": ANY,
        "user_key": title,
        "person": [{"uuid": mo_person}],
        "org_unit": [{"uuid": mo_org_unit}],
        "engagement_type": {"user_key": "Ansat"},
        "job_function": {"user_key": "Jurist"},
        "primary": {"user_key": "primary"},
        "extension_1": title,
        "validity": {"from_": mo_today(), "to": None},
    }
    await assert_engagement(mo_engagement)

    # LDAP: Edit
    title = "edit"
    await ldap_modify(
        ldap_connection,
        dn=person_dn,
        changes={
            "title": [("MODIFY_REPLACE", title)],
        },
    )
    mo_engagement = {
        **mo_engagement,
        "user_key": title,
        "extension_1": title,
    }
    await assert_engagement(mo_engagement)

    # LDAP: Terminate
    await ldap_modify(
        ldap_connection,
        dn=person_dn,
        changes={
            "carLicense": [("MODIFY_REPLACE", "EXPIRED")],
        },
    )
    mo_engagement = {
        **mo_engagement,
        "validity": {"from_": mo_today(), "to": mo_today()},
    }
    await assert_engagement(mo_engagement)


@pytest.mark.integration_test
@pytest.mark.envvar(
    {
        "LISTEN_TO_CHANGES_IN_MO": "True",
        "LISTEN_TO_CHANGES_IN_LDAP": "False",
        "CONVERSION_MAPPING": json.dumps(
            {
                "ldap_to_mo": {},
                "mo2ldap": """
                {% set mo_employee_engagement = load_mo_primary_engagement(uuid) %}
                {{
                    {
                        "title": mo_employee_engagement.user_key if mo_employee_engagement else [],
                        "departmentNumber": mo_employee_engagement.org_unit.uuid | string if mo_employee_engagement else []
                    }|tojson
                }}
                """,
                "mo_to_ldap": {},
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
    mo_org_unit: UUID,
    ldap_connection: Connection,
    ldap_org: list[str],
    ansat: UUID,
    jurist: UUID,
    primary: UUID,
) -> None:
    cpr = "2108613133"

    @retry()
    async def assert_engagement(expected: dict[str, Any]) -> None:
        response, _ = await ldap_search(
            ldap_connection,
            search_base=combine_dn_strings(ldap_org),
            search_filter=f"(employeeNumber={cpr})",
            attributes=["title", "departmentNumber"],
        )
        assert one(response)["attributes"] == expected

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
    await assert_engagement({"title": [], "departmentNumber": []})

    # MO: Create
    title = "create"
    mo_engagement = await graphql_client.engagement_create(
        input=EngagementCreateInput(
            user_key=title,
            person=mo_person,
            org_unit=mo_org_unit,
            engagement_type=ansat,
            job_function=jurist,
            primary=primary,
            extension_1=title,
            validity={"from": "2001-02-03T04:05:06Z"},
        )
    )
    await assert_engagement({"title": [title], "departmentNumber": [str(mo_org_unit)]})

    # MO: Edit
    title = "update"
    await graphql_client.engagement_update(
        input=EngagementUpdateInput(
            uuid=mo_engagement.uuid,
            user_key=title,
            validity={"from": "2011-12-13T14:15:16Z"},
            # TODO: why is this required?
            person=mo_person,
            org_unit=mo_org_unit,
            engagement_type=ansat,
            job_function=jurist,
            primary=primary,
            extension_1=title,
        )
    )
    await assert_engagement({"title": [title], "departmentNumber": [str(mo_org_unit)]})

    # MO: Terminate
    await graphql_client.engagement_terminate(
        input=EngagementTerminateInput(
            uuid=mo_engagement.uuid,
            to=mo_today(),
        ),
    )
    await assert_engagement({"title": [], "departmentNumber": []})
