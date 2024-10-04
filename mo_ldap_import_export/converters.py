# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
import json
from collections import ChainMap
from collections.abc import MutableMapping
from datetime import datetime
from datetime import time
from json.decoder import JSONDecodeError
from typing import Any
from typing import cast
from uuid import UUID
from uuid import uuid4

import pydantic
import structlog
from jinja2 import Environment
from jinja2 import Template
from ldap3.utils.ciDict import CaseInsensitiveDict
from more_itertools import one
from more_itertools import only
from pydantic import Field

from .autogenerated_graphql_client.client import GraphQLClient
from .config import Settings
from .config import get_required_attributes
from .dataloaders import DataLoader
from .exceptions import IncorrectMapping
from .ldap_classes import LdapObject
from .types import DN
from .utils import delete_keys_from_dict
from .utils import is_list

logger = structlog.stdlib.get_logger()


async def get_itsystem_user_keys(graphql_client: GraphQLClient) -> set[str]:
    result = await graphql_client.read_itsystems()
    return {obj.current.user_key for obj in result.objects if obj.current is not None}


async def find_cpr_field(mapping: dict[str, Any]) -> str | None:
    """Get the field which contains the CPR number in LDAP.

    Args:
        mapping: The raw mapping configuration.

    Raises:
        IncorrectMapping: Raised if 'Employee' is missing in the mapping.

    Returns:
        The CPR field if found, otherwise None
    """
    try:
        employee_mapping = mapping["mo_to_ldap"]["Employee"]
    except KeyError as error:
        raise IncorrectMapping("Missing 'Employee' in mapping 'mo_to_ldap'") from error

    cpr_fields = [
        ldap_field_name
        for ldap_field_name, template_string in employee_mapping.items()
        if "mo_employee.cpr_no" in template_string
    ]
    cpr_field = only(cpr_fields)
    if cpr_field:
        logger.info("Found CPR field in LDAP", cpr_field=cpr_field)
        return cast(str, cpr_field)

    logger.warning("CPR field not found")
    return None


async def find_ldap_it_system(
    graphql_client: GraphQLClient, settings: Settings, mapping: dict[str, Any]
) -> str | None:
    """
    Loop over all of MO's IT-systems and determine if one of them contains the AD-DN
    as a user_key
    """
    mo_it_system_user_keys = await get_itsystem_user_keys(graphql_client)

    detection_key = str(uuid4())
    relevant_keys: set[str] = mo_it_system_user_keys & mapping["ldap_to_mo"].keys()

    async def template_contains_unique_field(user_key: str) -> bool:
        """Check if the template found at user-key utilizes the unique id.

        The check is done by templating the unique id using a known string and checking
        whether the known string is in the output.
        """
        # TODO: XXX: Could we simply check the template string??
        template = mapping["ldap_to_mo"][user_key]["user_key"]
        unique_id: str = await template.render_async(
            {"ldap": {settings.ldap_unique_id_field: detection_key}}
        )
        return unique_id == detection_key

    found_itsystems = {
        user_key
        for user_key in relevant_keys
        if await template_contains_unique_field(user_key)
    }
    if len(found_itsystems) == 0:
        logger.warning("LDAP IT-system not found")
        return None
    if len(found_itsystems) > 1:
        logger.error("Multiple LDAP IT-system found!")
        return None
    found_itsystem = one(found_itsystems)
    logger.info("Found LDAP IT-system", itsystem=found_itsystem)
    return found_itsystem


class LdapConverter:
    def __init__(self, settings: Settings, dataloader: DataLoader) -> None:
        self.settings = settings
        self.dataloader = dataloader

    async def _init(self):
        raw_mapping = self.settings.conversion_mapping.dict(
            exclude_unset=True, by_alias=True
        )
        mapping = delete_keys_from_dict(
            raw_mapping,
            ["objectClass", "_import_to_mo_", "_export_to_ldap_"],
        )

        from .environments import construct_environment

        environment = construct_environment(self.settings, self.dataloader)
        self.mapping = self._populate_mapping_with_templates(mapping, environment)

        self.cpr_field = await find_cpr_field(mapping)

        self.ldap_it_system = await find_ldap_it_system(
            self.dataloader.graphql_client, self.settings, self.mapping
        )
        await self.check_mapping()

    def find_ldap_object_class(self, json_key):
        return self.settings.conversion_mapping.mo_to_ldap[json_key].objectClass

    def get_ldap_attributes(self, json_key, remove_dn=True):
        ldap_attributes = list(self.mapping["mo_to_ldap"][json_key].keys())
        if "dn" in ldap_attributes and remove_dn:
            # "dn" is the key which all LDAP objects have, not an attribute.
            ldap_attributes.remove("dn")
        return ldap_attributes

    def get_mo_attributes(self, json_key):
        return list(self.mapping["ldap_to_mo"][json_key].keys())

    def check_cpr_field_or_it_system(self):
        """
        Check that we have either a cpr-field OR an it-system which maps to an LDAP DN
        """
        if not self.cpr_field and not self.ldap_it_system:
            raise IncorrectMapping(
                "Neither a cpr-field or an ldap it-system could be found"
            )

    async def check_mapping(self) -> None:
        """Check if the configured mapping is valid.

        Args:
            mapping: The raw mapping configuration.

        Raises:
            IncorrectMapping: Raised if the mapping is invalid.
        """

        logger.info("Checking json file")

        # Check to see if there is an existing link between LDAP and MO
        self.check_cpr_field_or_it_system()

        logger.info("Attributes OK")

    @staticmethod
    def str_to_dict(text):
        """
        Converts a string to a dictionary
        """
        return json.loads(text.replace("'", '"').replace("Undefined", "null"))

    def string2template(
        self, environment: Environment, template_string: str
    ) -> Template:
        return environment.from_string(template_string)

    def _populate_mapping_with_templates(
        self, mapping: dict[str, Any], environment: Environment
    ) -> dict[str, Any]:
        def populate_value(value: str | dict[str, Any]) -> Any:
            if isinstance(value, str):
                return self.string2template(environment, value)
            if isinstance(value, dict):
                return self._populate_mapping_with_templates(value, environment)
            # TODO: Validate all types here in the future, for now accept whatever
            return value

        return {key: populate_value(value) for key, value in mapping.items()}

    async def to_ldap(
        self, mo_object_dict: MutableMapping[str, Any], json_key: str, dn: DN
    ) -> LdapObject:
        """
        Args:
            mo_object_dict:
                Template context for mapping templates.

                Example:
                    ```
                        {
                            'mo_employee': Employee,
                            'mo_address': Address
                        }
                    ```

                Where `Employee` and `Address` are imported from ramodels.

                Must always have 'mo_employee'.

            json_key:
                Key to look for in the mapping dict.

                Examples:
                    - Employee
                    - mail_address_attributes

            dn: DN of the LDAP account to synchronize to.
        """
        ldap_object = {}
        assert "mo_employee" in mo_object_dict

        # Globals
        mo_template_dict = ChainMap({"dn": dn}, mo_object_dict)
        try:
            object_mapping = self.mapping["mo_to_ldap"][json_key]
        except KeyError as error:
            raise IncorrectMapping(
                f"Missing '{json_key}' in mapping 'mo_to_ldap'"
            ) from error

        # TODO: Test what happens with exceptions here
        for ldap_field_name, template in object_mapping.items():
            rendered_item = await template.render_async(mo_template_dict)
            if rendered_item:
                ldap_object[ldap_field_name] = rendered_item

        if "dn" not in ldap_object:
            ldap_object["dn"] = dn

        return LdapObject(**ldap_object)

    def get_number_of_entries(self, ldap_object: LdapObject) -> int:
        """Returns the maximum cardinality of data fields within an LdapObject.

        If a given data field has multiple values it will be a list within the
        ldap_object, we wish to find the length of the longest list.

        Non list data fields will be interpreted as having length 1.

        Args:
            ldap_object: The object to find the maximum cardinality within.

        Returns:
            The maximum cardinality contained within ldap_object.
            Will always return atleast 1 as the ldap_object always contains a DN.
        """

        def ldap_field2cardinality(value: Any) -> int:
            if isinstance(value, list):
                return len(value)
            return 1

        values = ldap_object.dict().values()
        cardinality_values = map(ldap_field2cardinality, values)
        return max(cardinality_values)

    async def from_ldap(
        self,
        ldap_object: LdapObject,
        json_key: str,
        employee_uuid: UUID,
    ) -> Any:
        """
        uuid : UUID
            Uuid of the employee whom this object belongs to. If None: Generates a new
            uuid
        """

        # This is how many MO objects we need to return - a MO object can have only
        # One value per field. Not multiple. LDAP objects however, can have multiple
        # values per field.
        number_of_entries = self.get_number_of_entries(ldap_object)

        converted_objects = []
        for entry in range(number_of_entries):
            ldap_dict: CaseInsensitiveDict = CaseInsensitiveDict(
                {
                    key: (
                        value[min(entry, len(value) - 1)]
                        if is_list(value) and len(value) > 0
                        else value
                    )
                    for key, value in ldap_object.dict().items()
                }
            )
            context = {
                "ldap": ldap_dict,
                "employee_uuid": str(employee_uuid),
            }
            try:
                object_mapping = self.mapping["ldap_to_mo"][json_key]
            except KeyError as error:
                raise IncorrectMapping(
                    f"Missing '{json_key}' in mapping 'ldap_to_mo'"
                ) from error

            async def render_template(field_name: str, template, context) -> Any:
                value = (await template.render_async(context)).strip()

                # Sloppy mapping can lead to the following rendered strings:
                # - {{ldap.mail or None}} renders as "None"
                # - {{ldap.mail}} renders as "[]" if ldap.mail is empty
                #
                # Mapping with {{ldap.mail or NONE}} solves both, but let's check
                # for "none" or "[]" strings anyway to be more robust.
                if value.lower() == "none" or value == "[]":
                    value = ""

                # TODO: Is it possible to render a dictionary directly?
                #       Instead of converting from a string
                if "{" in value and ":" in value and "}" in value:
                    try:
                        value = self.str_to_dict(value)
                    except JSONDecodeError as error:
                        error_string = f"Could not convert {value} in {json_key}['{field_name}'] to dict (context={context!r})"
                        raise IncorrectMapping(error_string) from error
                return value

            # TODO: asyncio.gather this for future dataloader bulking
            mo_dict = {
                mo_field_name: await render_template(mo_field_name, template, context)
                for mo_field_name, template in object_mapping.items()
                # Remove the mapper key from the output, as it is not needed to create
                # the objects themselves, rather only later for mapping of objects
                if mo_field_name != "_mapper_"
            }
            mo_class = self.settings.conversion_mapping.ldap_to_mo[
                json_key
            ].as_mo_class()
            required_attributes = get_required_attributes(mo_class)

            # Load our validity default, if it is not set
            missing_attributes = required_attributes - set(mo_dict.keys())
            if "validity" in required_attributes:
                assert (
                    "validity" not in mo_dict
                ), "validity disallowed in ldap2mo mappings"
                mo_dict["validity"] = {
                    # TODO: We probably want to use datetime.now(UTC) here, and then
                    #       pass that value all the way through the program till the
                    #       GraphQL code that uploads it to MO, such that it is easier
                    #       to clean up later when MO supports proper datetimes.
                    "from": datetime.combine(datetime.today(), time()),
                    "to": None,
                }

            # If any required attributes are missing
            missing_attributes = required_attributes - set(mo_dict.keys())
            # TODO: Restructure this so rejection happens during parsing?
            if missing_attributes:  # pragma: no cover
                logger.info(
                    "Missing attributes in dict to model conversion",
                    mo_dict=mo_dict,
                    mo_class=mo_class,
                    missing_attributes=missing_attributes,
                )
                raise ValueError("Missing attributes in dict to model conversion")

            # Remove empty values
            mo_dict = {key: value for key, value in mo_dict.items() if value}
            # If any required attributes are missing
            missing_attributes = required_attributes - set(mo_dict.keys())
            if missing_attributes:  # pragma: no cover
                logger.info(
                    "Missing values in LDAP to synchronize, skipping",
                    mo_dict=mo_dict,
                    mo_class=mo_class,
                    missing_attributes=missing_attributes,
                )
                continue

            # If requested to terminate, we generate and return a termination subclass
            # instead of the original class. This is to ensure we can forward the termination date,
            # without having to modify the RAModel.
            if "_terminate_" in mo_dict:
                # TODO: Fix typing of mo_class to be MOBase instead of just type
                class Termination(mo_class):  # type: ignore
                    # TODO: we use alias because fields starting with underscore are
                    # considered private by Pydantic. This entire hack should be
                    # removed in favour of properly passing Verb.TERMINATE around.
                    terminate_: str | None = Field(alias="_terminate_")

                    class Config:
                        allow_population_by_field_name = True

                mo_dict["terminate_"] = mo_dict.pop("_terminate_")
                mo_class = Termination

            try:
                converted_objects.append(mo_class(**mo_dict))
            except pydantic.ValidationError:
                logger.info("Exception during object parsing", exc_info=True)

        return converted_objects
