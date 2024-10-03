# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
from unittest.mock import ANY

import pytest
from httpx import AsyncClient


@pytest.mark.usefixtures("ldap_person")
@pytest.mark.integration_test
async def test_inspect_overview_populated(test_client: AsyncClient) -> None:
    response = await test_client.get("/Inspect/overview/populated")
    assert response.status_code == 202

    result = response.json()
    assert result == {
        "attributes": ANY,
        "superiors": ["organizationalPerson", "person", "top"],
    }

    # Check the populated attributes are as expected
    attributes = result["attributes"].keys()
    assert attributes == {
        "cn",
        "employeeNumber",
        "givenName",
        "mail",
        "objectClass",
        "ou",
        "sn",
        "title",
        "uid",
        "userPassword",
    }

    # Check a single attribute has the details we expect
    assert result["attributes"]["title"] == {
        "example_value": ["Skole underviser"],
        "single_value": False,
        "syntax": None,
    }


@pytest.mark.usefixtures("ldap_org")
@pytest.mark.integration_test
async def test_inspect_overview_populated_organizational_unit(
    test_client: AsyncClient,
) -> None:
    response = await test_client.get(
        "/Inspect/overview/populated", params={"ldap_class": "organizationalUnit"}
    )
    assert response.status_code == 202

    result = response.json()
    assert result == {
        "attributes": ANY,
        "superiors": ["top"],
    }

    # Check the populated attributes are as expected
    attributes = result["attributes"].keys()
    assert attributes == {"objectClass", "ou"}

    # Check a single attribute has the details we expect
    assert result["attributes"]["ou"] == {
        "example_value": ["os2mo"],
        "single_value": False,
        "syntax": None,
    }
