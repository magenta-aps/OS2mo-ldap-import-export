import json
import os
from unittest.mock import MagicMock

import pandas as pd
import pytest
from fastramqpi.context import Context

from mo_ldap_import_export.exporters import MappingExporter


@pytest.fixture
def context() -> Context:

    settings_mock = MagicMock()

    context: Context = {
        "user_context": {
            "settings": settings_mock,
        }
    }

    return context


def initialize_exporter(mapping, context):
    """
    Saves a mapping to json, reads it, exports it as an excel sheet and returns the
    sheets
    """

    with open("test_mapping.json", "w") as f:
        json.dump(mapping, f)

    exporter = MappingExporter(
        context,
        "test_mapping.json",
        output_filename="Mapping.xlsx",
    )
    exporter.export_mapping()

    ad_to_mo_mapping = pd.read_excel("Mapping.xlsx", sheet_name=0)
    mo_to_ad_mapping = pd.read_excel("Mapping.xlsx", sheet_name=1)

    os.remove("test_mapping.json")
    os.remove("Mapping.xlsx")

    return ad_to_mo_mapping, mo_to_ad_mapping


def test_basic_json_file(context: Context):

    mapping = {
        "ldap_to_mo": {
            "Employee": {
                "objectClass": "ramodels.mo.employee.Employee",
                "_import_to_mo_": "True",
                "givenname": "{{ldap.givenName}}",
            },
        },
        "mo_to_ldap": {
            "Employee": {
                "objectClass": "user",
                "_export_to_ldap_": "True",
                "givenName": "{{mo_employee.givenname}}",
            },
        },
    }
    ad_to_mo_mapping, mo_to_ad_mapping = initialize_exporter(mapping, context)

    assert ad_to_mo_mapping.loc[0, "user_key"] == "Employee"
    assert ad_to_mo_mapping.loc[0, "MO object class"] == "Employee"
    assert ad_to_mo_mapping.loc[0, "MO attribute"] == "givenname"
    assert ad_to_mo_mapping.loc[0, "MO-to-AD"] == "x"
    assert ad_to_mo_mapping.loc[0, "AD-to-MO"] == "x"
    assert ad_to_mo_mapping.loc[0, "AD-to-MO (manual import)"] == "x"
    assert ad_to_mo_mapping.loc[0, "AD attribute(s)"] == "givenName"
    assert ad_to_mo_mapping.loc[0, "template"] == "{{ldap.givenName}}"

    assert mo_to_ad_mapping.loc[0, "user_key"] == "Employee"
    assert mo_to_ad_mapping.loc[0, "AD object class"] == "user"
    assert mo_to_ad_mapping.loc[0, "AD attribute"] == "givenName"
    assert mo_to_ad_mapping.loc[0, "MO-to-AD"] == "x"
    assert mo_to_ad_mapping.loc[0, "AD-to-MO"] == "x"
    assert mo_to_ad_mapping.loc[0, "AD-to-MO (manual import)"] == "x"
    assert mo_to_ad_mapping.loc[0, "MO attribute(s)"] == "givenname"
    assert mo_to_ad_mapping.loc[0, "template"] == "{{mo_employee.givenname}}"
