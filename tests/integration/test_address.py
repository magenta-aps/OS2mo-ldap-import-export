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

from mo_ldap_import_export.autogenerated_graphql_client import AddressCreateInput
from mo_ldap_import_export.autogenerated_graphql_client import AddressFilter
from mo_ldap_import_export.autogenerated_graphql_client import AddressUpdateInput
from mo_ldap_import_export.autogenerated_graphql_client import EmployeeFilter
from mo_ldap_import_export.autogenerated_graphql_client import GraphQLClient
from mo_ldap_import_export.ldap import ldap_add
from mo_ldap_import_export.ldap import ldap_modify
from mo_ldap_import_export.ldap import ldap_search
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
                    "EmailEmployee": {
                        "objectClass": "ramodels.mo.details.address.Address",
                        "_import_to_mo_": "true",
                        "_mapper_": "{{ obj.address_type }}",
                        # carLicense is arbitrarily chosen as an enabled/disabled marker
                        "_terminate_": "{{ now()|mo_datestring if ldap.carLicense == 'EXPIRED' else NONE}}",
                        "value": "{{ ldap.mail }}",
                        "address_type": "{{ dict(uuid=get_employee_address_type_uuid('EmailEmployee')) }}",
                        "person": "{{ dict(uuid=employee_uuid ) }}",
                        "visibility": "{{ dict(uuid=get_visibility_uuid('Public')) }}",
                    },
                },
                # TODO: why is this required?
                "mo_to_ldap": {
                    "Employee": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "false",
                        "employeeNumber": "{{mo_employee.cpr_no}}",
                    },
                    "EmailEmployee": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "false",
                        "mail": "{{ mo_employee_address.value }}",
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
    async def assert_address(expected: dict) -> None:
        addresses = await graphql_client._testing__address_read(
            filter=AddressFilter(
                employee=EmployeeFilter(uuids=[mo_person]),
            ),
        )
        address = one(addresses.objects)
        validities = one(address.validities)
        assert validities.dict() == expected

    person_dn = combine_dn_strings(["uid=abk"] + ldap_org)

    # LDAP: Create
    mail = "create@example.com"
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
            "mail": mail,
            "carLicense": "ACTIVE",
        },
    )
    mo_address = {
        "uuid": ANY,
        "user_key": ANY,
        "address_type": {"user_key": "EmailEmployee"},
        "value": mail,
        "value2": None,
        "person": [{"uuid": mo_person}],
        "visibility": {"user_key": "Public"},
        "validity": {"from_": mo_today(), "to": None},
    }
    await assert_address(mo_address)

    # LDAP: Edit
    mail = "edit@example.com"
    await ldap_modify(
        ldap_connection,
        dn=person_dn,
        changes={
            "mail": [("MODIFY_REPLACE", mail)],
        },
    )
    mo_address = {
        **mo_address,
        "value": mail,
    }
    await assert_address(mo_address)

    # LDAP: Terminate
    await ldap_modify(
        ldap_connection,
        dn=person_dn,
        changes={
            "carLicense": [("MODIFY_REPLACE", "EXPIRED")],
        },
    )
    mo_address = {
        **mo_address,
        "validity": {"from_": mo_today(), "to": mo_today()},
    }
    await assert_address(mo_address)


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
                    "EmailEmployee": {
                        "objectClass": "ramodels.mo.details.address.Address",
                        "_import_to_mo_": "false",
                        "_mapper_": "{{ obj.address_type }}",
                        "value": "{{ ldap.mail }}",
                        "address_type": "{{ dict(uuid=get_employee_address_type_uuid('EmailEmployee')) }}",
                        "person": "{{ dict(uuid=employee_uuid ) }}",
                        "visibility": "{{ dict(uuid=get_visibility_uuid('Public')) }}",
                    },
                },
                "mo_to_ldap": {
                    "Employee": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "false",
                        "employeeNumber": "{{mo_employee.cpr_no}}",
                    },
                    "EmailEmployee": {
                        "objectClass": "inetOrgPerson",
                        "_export_to_ldap_": "true",
                        "mail": "{{ mo_employee_address.value }}",
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
    mo_person: UUID,
    ldap_connection: Connection,
    ldap_org: list[str],
) -> None:
    cpr = "2108613133"

    @retry()
    async def assert_address(expected: dict[str, Any]) -> None:
        response, _ = await ldap_search(
            ldap_connection,
            search_base=combine_dn_strings(ldap_org),
            search_filter=f"(employeeNumber={cpr})",
            attributes=["mail"],
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
    await assert_address({"mail": []})

    # MO: Create
    address_type = one(
        (
            await graphql_client.read_class_uuid_by_facet_and_class_user_key(
                "employee_address_type", "EmailEmployee"
            )
        ).objects
    ).uuid
    visibility = one(
        (
            await graphql_client.read_class_uuid_by_facet_and_class_user_key(
                "visibility", "Public"
            )
        ).objects
    ).uuid

    mail = "create@example.com"
    mo_address = await graphql_client._testing_address_create(
        input=AddressCreateInput(
            user_key="test address",
            address_type=address_type,
            value=mail,
            person=mo_person,
            visibility=visibility,
            validity={"from": "2001-02-03T04:05:06Z"},
        )
    )
    await assert_address({"mail": [mail]})

    # MO: Edit
    mail = "update@example.com"
    await graphql_client._testing_address_update(
        input=AddressUpdateInput(
            uuid=mo_address.uuid,
            value=mail,
            validity={"from": "2011-12-13T14:15:16Z"},
            # TODO: why is this required?
            user_key="test address",
            address_type=address_type,
            person=mo_person,
            visibility=visibility,
        )
    )
    await assert_address({"mail": [mail]})

    # MO: Terminate
    await graphql_client._testing_address_terminate(
        uuid=mo_address.uuid,
        to=mo_today(),
    )
    await assert_address({"mail": []})
