import copy
import os.path
import uuid
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

import pytest
from fastramqpi.context import Context
from ramodels.mo import Employee

from mo_ldap_import_export.converters import LdapConverter
from mo_ldap_import_export.converters import read_mapping_json
from mo_ldap_import_export.dataloaders import LdapObject
from mo_ldap_import_export.exceptions import CprNoNotFound
from mo_ldap_import_export.exceptions import IncorrectMapping


@pytest.fixture
def context() -> Context:

    mapping = {
        "ldap_to_mo": {
            "Employee": {
                "objectClass": "ramodels.mo.employee.Employee",
                "givenname": "{{ldap.GivenName}}",
                "surname": "{{ldap.sn}}",
            }
        },
        "mo_to_ldap": {
            "Employee": {
                "objectClass": "user",
                "givenName": "{{mo_employee.givenname}}",
                "sn": "{{mo_employee.surname}}",
                "displayName": "{{mo_employee.surname}}, {{mo_employee.givenname}}",
                "name": "{{mo_employee.givenname}} {{mo_employee.surname}}",
                "dn": "",
                "employeeID": "{{mo_employee.cpr_no or None}}",
            }
        },
    }

    settings_mock = MagicMock()
    settings_mock.ldap_organizational_unit = "foo"
    settings_mock.ldap_search_base = "bar"

    dataloader = AsyncMock()
    mo_address_types = {"uuid1": "Email", "uuid2": "Post"}

    load_mo_address_types = MagicMock()
    load_mo_address_types.return_value = mo_address_types
    dataloader.load_mo_address_types = load_mo_address_types

    context: Context = {
        "user_context": {
            "mapping": mapping,
            "settings": settings_mock,
            "dataloader": dataloader,
        }
    }
    return context


def test_ldap_to_mo(context: Context) -> None:
    converter = LdapConverter(context)
    employee = converter.from_ldap(
        LdapObject(
            dn="",
            name="",
            givenName="Tester",
            sn="Testersen",
            objectGUID="{" + str(uuid.uuid4()) + "}",
            cpr="0101011234",
        ),
        "Employee",
    )
    assert employee.givenname == "Tester"
    assert employee.surname == "Testersen"


def test_mo_to_ldap(context: Context) -> None:
    converter = LdapConverter(context)
    obj_dict = {"mo_employee": Employee(givenname="Tester", surname="Testersen")}
    ldap_object: Any = converter.to_ldap(obj_dict, "Employee")
    assert ldap_object.givenName == "Tester"
    assert ldap_object.sn == "Testersen"
    assert ldap_object.name == "Tester Testersen"


def test_mapping_loader() -> None:
    mapping = read_mapping_json(
        os.path.join(os.path.dirname(__file__), "resources", "mapping.json")
    )
    expected = {
        "ldap_to_mo": {
            "Employee": {
                "objectClass": "ramodels.mo.employee.Employee",
                "givenname": "{{ldap.givenName or ldap.name|splitlast|first}}",
                "surname": "{{ldap.surname or ldap.sn or "
                "ldap.name|splitlast|last or ''}}",
                "cpr_no": "{{ldap.cpr or None}}",
                "seniority": "{{ldap.seniority or None}}",
                "nickname_givenname": "{{ldap.nickname_givenname or None}}",
                "nickname_surname": "{{ldap.nickname_surname or None}}",
            }
        },
        "mo_to_ldap": {
            "Employee": {
                "objectClass": "user",
                "givenName": "{{mo_employee.givenname}}",
                "sn": "{{mo_employee.surname}}",
                "displayName": "{{mo_employee.surname}}, {{mo_employee.givenname}}",
                "name": "{{mo_employee.givenname}} {{mo_employee.surname}}",
                "cpr": "{{mo_employee.cpr_no or None}}",
                "seniority": "{{mo_employee.seniority or None}}",
                "nickname_givenname": "{{mo_employee.nickname_givenname or None}}",
                "nickname_surname": "{{mo_employee.nickname_surname or None}}",
            }
        },
    }
    assert mapping == expected


def test_mapping_loader_failure(context: Context) -> None:

    good_mapping = {
        "ldap_to_mo": {
            "Employee": {
                "objectClass": "ramodels.mo.employee.Employee",
                "givenname": "{{ldap.givenName or ldap.name|splitlast|first}}",
                "surname": "{{ldap.surname or ldap.sn or "
                "ldap.name|splitlast|last or ''}}",
                "cpr_no": "{{ldap.cpr or None}}",
                "seniority": "{{ldap.seniority or None}}",
                "nickname_givenname": "{{ldap.nickname_givenname or None}}",
                "nickname_surname": "{{ldap.nickname_surname or None}}",
            }
        },
        "mo_to_ldap": {
            "Employee": {
                "objectClass": "user",
                "givenName": "{{mo_employee.givenname}}",
                "sn": "{{mo_employee.surname}}",
                "displayName": "{{mo_employee.surname}}, {{mo_employee.givenname}}",
                "name": "{{mo_employee.givenname}} {{mo_employee.surname}}",
                "cpr": "{{mo_employee.cpr_no or None}}",
                "seniority": "{{mo_employee.seniority or None}}",
                "nickname_givenname": "{{mo_employee.nickname_givenname or None}}",
                "nickname_surname": "{{mo_employee.nickname_surname or None}}",
            }
        },
    }

    good_context = copy.deepcopy(context)
    good_context["user_context"]["mapping"] = good_mapping

    for bad_mapping in ({}, {"ldap_to_mo": {}}, {"mo_to_ldap": {}}):

        bad_context = copy.deepcopy(context)
        bad_context["user_context"]["mapping"] = bad_mapping

        with pytest.raises(IncorrectMapping):
            LdapConverter(context=bad_context)
        with pytest.raises(IncorrectMapping):
            LdapConverter(context=bad_context)

        converter = LdapConverter(context=good_context)
        converter.mapping = bad_mapping
        with pytest.raises(IncorrectMapping):
            converter.from_ldap(
                LdapObject(
                    dn="",
                    name="",
                    givenName="Tester",
                    sn="Testersen",
                    objectGUID="{" + str(uuid.uuid4()) + "}",
                    cpr="0101011234",
                ),
                "Employee",
            )
        with pytest.raises(IncorrectMapping):
            obj_dict = {
                "mo_employee": Employee(givenname="Tester", surname="Testersen")
            }
            converter.to_ldap(obj_dict, "Employee")


def test_splitfirst() -> None:
    assert LdapConverter.filter_splitfirst("Test") == ["Test", ""]
    assert LdapConverter.filter_splitfirst("Test Testersen") == [
        "Test",
        "Testersen",
    ]
    assert LdapConverter.filter_splitfirst("Test Testersen med test") == [
        "Test",
        "Testersen med test",
    ]
    assert LdapConverter.filter_splitfirst("") == ["", ""]


def test_splitlast() -> None:
    assert LdapConverter.filter_splitlast("Test") == ["", "Test"]
    assert LdapConverter.filter_splitlast("Test Testersen") == ["Test", "Testersen"]
    assert LdapConverter.filter_splitlast("Test Testersen med test") == [
        "Test Testersen med",
        "test",
    ]
    assert LdapConverter.filter_splitlast("") == ["", ""]


def test_find_cpr_field(context: Context) -> None:

    # This mapping is accepted
    good_mapping = {
        "mo_to_ldap": {
            "Employee": {
                "objectClass": "user",
                "employeeID": "{{mo_employee.cpr_no or None}}",
            }
        },
    }

    # This mapping does not contain the mo_employee.cpr_no field
    bad_mapping = {
        "mo_to_ldap": {
            "Employee": {
                "objectClass": "user",
                "givenName": "{{mo_employee.givenname}}",
            }
        },
    }

    # Test both cases
    context["user_context"]["mapping"] = good_mapping
    converter = LdapConverter(context)
    assert converter.cpr_field == "employeeID"

    with pytest.raises(CprNoNotFound):
        context["user_context"]["mapping"] = bad_mapping
        converter = LdapConverter(context)


def test_template_lenience(context: Context) -> None:

    mapping = {
        "ldap_to_mo": {
            "Employee": {
                "objectClass": "ramodels.mo.employee.Employee",
                "givenname": "{{ldap.GivenName}}",
                "surname": "{{ldap.sn}}",
            }
        },
        "mo_to_ldap": {
            "Employee": {
                "objectClass": "user",
                "givenName": "{{mo_employee.givenname}}",
                "sn": "{{mo_employee.surname}}",
                "displayName": "{{mo_employee.surname}}, {{mo_employee.givenname}}",
                "name": "{{mo_employee.givenname}} {{mo_employee.surname}}",
                "dn": "",
                "employeeID": "{{mo_employee.cpr_no or None}}",
            }
        },
    }

    context["user_context"]["mapping"] = mapping
    converter = LdapConverter(context)
    converter.from_ldap(
        LdapObject(
            dn="",
            cpr="1234567890",
        ),
        "Employee",
    )


def test_find_object_class(context: Context):
    converter = LdapConverter(context)

    output = converter.find_object_class("Employee", "ldap_to_mo")
    assert output == "ramodels.mo.employee.Employee"

    output = converter.find_object_class("Employee", "mo_to_ldap")
    assert output == "user"

    with pytest.raises(IncorrectMapping):
        converter.find_object_class("non_existing_json_key", "mo_to_ldap")


def test_find_ldap_object_class(context: Context):
    converter = LdapConverter(context)
    object_class = converter.find_ldap_object_class("Employee")
    assert object_class == "user"


def test_find_mo_object_class(context: Context):
    converter = LdapConverter(context)
    object_class = converter.find_mo_object_class("Employee")
    assert object_class == "ramodels.mo.employee.Employee"


def test_get_ldap_attributes(context: Context):
    converter = LdapConverter(context)
    attributes = converter.get_ldap_attributes("Employee")

    all_attributes = list(
        context["user_context"]["mapping"]["mo_to_ldap"]["Employee"].keys()
    )

    expected_attributes = [a for a in all_attributes if a != "objectClass"]

    assert attributes == expected_attributes


def test_get_mo_attributes(context: Context):
    converter = LdapConverter(context)
    attributes = converter.get_mo_attributes("Employee")

    all_attributes = list(
        context["user_context"]["mapping"]["ldap_to_mo"]["Employee"].keys()
    )

    expected_attributes = [a for a in all_attributes if a != "objectClass"]

    assert attributes == expected_attributes


def test_check_attributes(context: Context):
    converter = LdapConverter(context)

    detected_attributes = ["foo", "bar"]
    accepted_attributes = ["bar"]

    with pytest.raises(IncorrectMapping):
        converter.check_attributes(detected_attributes, accepted_attributes)


def test_get_accepted_json_keys(context: Context):
    converter = LdapConverter(context)

    # dataloader = MagicMock()
    # mo_address_types = {"uuid1": "Email", "uuid2": "Post"}
    # dataloader.load_mo_address_types.return_value = mo_address_types

    # converter.dataloader = dataloader

    output = converter.get_accepted_json_keys()

    assert output == ["Employee", "Email", "Post"]


# async def test_check_mapping(context: Context):

#     context = copy.deepcopy(context)

#     # This mapping should trigger the first check
#     mapping = {
#         "ldap_to_mo": {
#             "Employee": {
#                 "objectClass": "ramodels.mo.employee.Employee",
#                 "givenname": "{{ldap.GivenName}}",
#                 "surname": "{{ldap.sn}}",
#             }
#         },
#         "mo_to_ldap": {
#             "Employee": {
#                 "objectClass": "user",
#                 "givenName": "{{mo_employee.givenname}}",
#                 "sn": "{{mo_employee.surname}}",
#                 "displayName": "{{mo_employee.surname}}, {{mo_employee.givenname}}",
#                 "name": "{{mo_employee.givenname}} {{mo_employee.surname}}",
#                 "dn": "",
#                 "employeeID": "{{mo_employee.cpr_no or None}}",
#             }
#         },
#     }

#     context["user_context"]["mapping"] = mapping

#     converter = LdapConverter(context)
#     async with converter.check_mapping():
#         pass

#     # Keep expanding 'mapping' until it is accepted
#     # See https://www.depends-on-the-definition.com/test-error-messages-with-pytest/
