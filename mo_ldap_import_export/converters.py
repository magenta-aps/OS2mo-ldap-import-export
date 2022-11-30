# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import copy
import datetime
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from typing import Dict

import structlog
from fastramqpi.context import Context
from jinja2 import Environment
from jinja2 import Undefined
from ldap3.utils.ciDict import CaseInsensitiveDict

from .exceptions import CprNoNotFound
from .exceptions import IncorrectMapping
from .exceptions import NotSupportedException
from .ldap_classes import LdapObject
from .utils import delete_keys_from_dict
from .utils import import_class


def read_mapping_json(filename: str) -> Any:
    with open(filename, "r") as file:
        data = "\n".join(file.readlines())
        data = re.sub("//[^\n]*", "", data)
        return json.loads(data)


def find_cpr_field(mapping):
    """
    Get the field which contains the CPR number in LDAP
    """
    logger = structlog.get_logger()
    try:
        mo_to_ldap = mapping["mo_to_ldap"]
    except KeyError:
        raise IncorrectMapping("Missing mapping 'mo_to_ldap'")
    try:
        Employee_mapping = mo_to_ldap["Employee"]
    except KeyError:
        raise IncorrectMapping("Missing 'Employee' in mapping 'mo_to_ldap'")

    # See if we can find a match for this search field/result
    search_result = "123"
    search_field = "cpr_no"

    mo_dict = {search_field: search_result}
    cpr_field = None
    for ldap_field_name, template in Employee_mapping.items():
        value = template.render({"mo_employee": mo_dict}).strip()

        if value == search_result:
            cpr_field = ldap_field_name
            logger.info(f"Found CPR field in LDAP: '{cpr_field}'")
            break

    if cpr_field is None:
        raise CprNoNotFound("CPR field not found")

    return cpr_field


class LdapConverter:
    def __init__(self, context: Context):

        self.context = context
        self.user_context = context["user_context"]
        self.settings = self.user_context["settings"]
        self.raw_mapping = self.user_context["mapping"]
        self.dataloader = self.user_context["dataloader"]

        mapping = delete_keys_from_dict(
            copy.deepcopy(self.raw_mapping), ["objectClass"]
        )

        environment = Environment(undefined=Undefined)
        environment.filters["splitlast"] = LdapConverter.filter_splitlast
        environment.filters["splitfirst"] = LdapConverter.filter_splitfirst
        environment.filters["strftime"] = LdapConverter.filter_strftime
        self.mapping = self._populate_mapping_with_templates(
            mapping,
            environment,
        )

        self.cpr_field = find_cpr_field(mapping)

    def find_object_class(self, json_key, conversion):
        mapping = self.raw_mapping[conversion]
        if json_key not in mapping.keys():
            raise IncorrectMapping(f"{json_key} not found in {conversion} json dict")
        else:
            return mapping[json_key]["objectClass"]

    def find_ldap_object_class(self, json_key):
        return self.find_object_class(json_key, "mo_to_ldap")

    def find_mo_object_class(self, json_key):
        return self.find_object_class(json_key, "ldap_to_mo")

    def import_mo_object_class(self, json_key):
        return import_class(self.find_mo_object_class(json_key))

    def get_ldap_attributes(self, json_key):
        return list(self.mapping["mo_to_ldap"][json_key].keys())

    def get_mo_attributes(self, json_key):
        return list(self.mapping["ldap_to_mo"][json_key].keys())

    def check_attributes(self, detected_attributes, accepted_attributes):
        for attribute in detected_attributes:
            if attribute not in accepted_attributes:
                raise IncorrectMapping(
                    (
                        f"attribute '{attribute}' not allowed."
                        f" Allowed attributes are {accepted_attributes}"
                    )
                )

    def get_accepted_json_keys(self) -> list[str]:

        mo_address_type_dict = self.dataloader.load_mo_address_types()
        mo_address_types = list(mo_address_type_dict.values())

        accepted_json_keys = ["Employee"] + mo_address_types
        return accepted_json_keys

    @asynccontextmanager
    async def check_mapping(self) -> AsyncIterator[None]:
        logger = structlog.get_logger()
        logger.info("[json check] Checking json file")
        mo_to_ldap_json_keys = list(self.mapping["mo_to_ldap"].keys())
        ldap_to_mo_json_keys = list(self.mapping["ldap_to_mo"].keys())
        json_keys = list(set(mo_to_ldap_json_keys + ldap_to_mo_json_keys))

        accepted_json_keys = self.get_accepted_json_keys()

        # 1. Check to make sure that all keys are valid
        logger.info(f"[json check] Accepted keys: {accepted_json_keys}")
        logger.info(f"[json check] Detected keys: {json_keys}")

        for key in json_keys:
            if key not in accepted_json_keys:
                raise IncorrectMapping(f"{key} is not a valid key")
        logger.info("[json check] Keys OK")

        # 2. check that the MO address attributes match the specified class
        for json_key in ldap_to_mo_json_keys:
            logger.info(f"[json check] checking ldap_to_mo[{json_key}]")

            mo_class = self.import_mo_object_class(json_key)

            accepted_attributes = list(mo_class.schema()["properties"].keys())
            detected_attributes = self.get_mo_attributes(json_key)
            if "required" in mo_class.schema().keys():
                required_attributes = mo_class.schema()["required"]
                for attribute in required_attributes:
                    if attribute not in detected_attributes:
                        raise IncorrectMapping(
                            (
                                f"attribute '{attribute}' is mandatory. "
                                f"The following attributes are mandatory: "
                                f"{required_attributes}"
                            )
                        )

            self.check_attributes(detected_attributes, accepted_attributes)

        # 3. check that the LDAP attributes match what is available in LDAP
        overview = await self.dataloader.load_ldap_overview()
        for json_key in mo_to_ldap_json_keys:
            logger.info(f"[json check] checking mo_to_ldap[{json_key}]")

            object_class = self.find_ldap_object_class(json_key)

            accepted_attributes = overview[object_class]["attributes"]
            detected_attributes = self.get_ldap_attributes(json_key)

            self.check_attributes(detected_attributes, accepted_attributes)

        logger.info("[json check] Attributes OK")

        yield

    @staticmethod
    def filter_splitfirst(text):
        """
        Splits a string at the first space, returning two elements
        This is convenient for splitting a name into a givenName and a surname
        and works for names with no spaces (surname will then be empty)
        """
        if text is not None:
            text = str(text)
            if text != "":
                s = text.split(" ", 1)
                return s if len(s) > 1 else (s + [""])
        return ["", ""]

    @staticmethod
    def nonejoin(*args):

        items_to_join = [a for a in args if a]
        return ", ".join(items_to_join)

    @staticmethod
    def str_to_dict(text):
        """
        Converts a string to a dictionary
        """
        return json.loads(text.replace("'", '"'))

    @staticmethod
    def filter_strftime(datetime_object):
        """
        Converts a string to a datestring with today's date
        """
        return datetime_object.strftime("%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def filter_splitlast(text):
        """
        Splits a string at the last space, returning two elements
        This is convenient for splitting a name into a givenName and a surname
        and works for names with no spaces (givenname will then be empty)
        """
        if text is not None:
            text = str(text)
            if text != "":
                text = str(text)
                s = text.split(" ")
                return [" ".join(s[:-1]), s[-1]]
        return ["", ""]

    def _populate_mapping_with_templates(
        self, mapping: Dict[str, Any], environment: Environment
    ):
        for key, value in mapping.items():
            if type(value) == str:
                mapping[key] = environment.from_string(value)
                mapping[key].globals["now"] = datetime.datetime.utcnow
                mapping[key].globals["nonejoin"] = self.nonejoin

            elif type(value) == dict:
                mapping[key] = self._populate_mapping_with_templates(value, environment)
        return mapping

    def to_ldap(self, mo_object_dict: dict, json_key: str) -> LdapObject:
        """
        mo_object_dict : dict
            dict with mo objects to convert. for example:
                {'mo_employee': Empoyee,
                 'mo_address': Address}

        json_key : str
            Key to look for in the mapping dict. For example:
                - Employee
                - mail_address_attributes
        """
        ldap_object = {}
        try:
            mapping = self.mapping["mo_to_ldap"]
        except KeyError:
            raise IncorrectMapping("Missing mapping 'mo_to_ldap'")
        try:
            object_mapping = mapping[json_key]
        except KeyError:
            raise IncorrectMapping(f"Missing '{json_key}' in mapping 'mo_to_ldap'")
        for ldap_field_name, template in object_mapping.items():
            rendered_item = template.render(mo_object_dict)
            ldap_object[ldap_field_name] = rendered_item

        if "mo_employee" in mo_object_dict.keys():
            mo_employee_object = mo_object_dict["mo_employee"]

            givenname = mo_employee_object.givenname
            surname = mo_employee_object.surname
            cpr_no = mo_employee_object.cpr_no or ""
            ldap_organizational_unit = self.settings.ldap_organizational_unit

            cn = f"CN={givenname} {surname} - {cpr_no}"  # Common Name
            ou = f"OU=Users,{ldap_organizational_unit}"  # Org. Unit
            dc = self.settings.ldap_search_base  # Domain Component
            dn = ",".join([cn, ou, dc])  # Distinguished Name
            ldap_object["dn"] = dn
        else:
            raise NotSupportedException(
                "Only cpr-indexed objects are supported by to_ldap"
            )

        return LdapObject(**ldap_object)

    def from_ldap(self, ldap_object: LdapObject, json_key: str) -> Any:
        ldap_dict = CaseInsensitiveDict(
            {
                key: value[0] if type(value) == list and len(value) == 1 else value
                for key, value in ldap_object.dict().items()
            }
        )
        mo_dict = {}
        try:
            mapping = self.mapping["ldap_to_mo"]
        except KeyError:
            raise IncorrectMapping("Missing mapping 'ldap_to_mo'")
        try:
            object_mapping = mapping[json_key]
        except KeyError:
            raise IncorrectMapping(f"Missing '{json_key}' in mapping 'ldap_to_mo'")
        for mo_field_name, template in object_mapping.items():

            value = template.render({"ldap": ldap_dict}).strip()

            # TODO: Is it possible to render a dictionary directly?
            #       Instead of converting from a string
            if "{" in value and ":" in value and "}" in value:
                value = self.str_to_dict(value)

            if (value != "None") and value:
                mo_dict[mo_field_name] = value

        mo_class: Any = self.import_mo_object_class(json_key)

        return mo_class(**mo_dict)
