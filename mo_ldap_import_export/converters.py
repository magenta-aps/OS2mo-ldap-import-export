# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
import json
import re
import string
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
from fastramqpi.ramqp.utils import RequeueMessage
from jinja2 import Environment
from jinja2 import Template
from ldap3.utils.ciDict import CaseInsensitiveDict
from more_itertools import one
from more_itertools import only
from pydantic import Field
from ramodels.mo import MOBase

from .autogenerated_graphql_client.client import GraphQLClient
from .config import Settings
from .dataloaders import DataLoader
from .exceptions import IncorrectMapping
from .ldap_classes import LdapObject
from .types import DN
from .utils import delete_keys_from_dict
from .utils import import_class
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
        mo_to_ldap = mapping["mo_to_ldap"]
    except KeyError as error:
        raise IncorrectMapping("Missing 'mo_to_ldap' in mapping") from error
    try:
        employee_mapping = mo_to_ldap["Employee"]
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
    def __init__(
        self, settings: Settings, raw_mapping: dict[str, Any], dataloader: DataLoader
    ) -> None:
        self.settings = settings
        self.raw_mapping = raw_mapping
        self.dataloader = dataloader

    async def _init(self):
        mapping = delete_keys_from_dict(
            self.raw_mapping,
            ["objectClass", "_import_to_mo_", "_export_to_ldap_"],
        )

        from .environments import construct_environment

        environment = construct_environment(self.settings, self.dataloader)
        self.mapping = self._populate_mapping_with_templates(mapping, environment)

        self.cpr_field = await find_cpr_field(mapping)

        self.ldap_it_system = await find_ldap_it_system(
            self.dataloader.graphql_client, self.settings, self.mapping
        )
        await self.check_mapping(mapping)

    def _export_to_ldap_(self, json_key):
        """
        Returns True, when we need to export this json key. Otherwise False
        """
        export_flag = self.raw_mapping["mo_to_ldap"][json_key][
            "_export_to_ldap_"
        ].lower()
        if export_flag == "pause":
            logger.info("_export_to_ldap_ = 'pause'. Requeueing.")
            raise RequeueMessage()
        return export_flag == "true"

    def find_object_class(self, json_key, conversion):
        mapping = self.raw_mapping[conversion]
        if json_key not in mapping:
            raise IncorrectMapping(f"{json_key} not found in {conversion} json dict")
        return mapping[json_key]["objectClass"]

    def find_ldap_object_class(self, json_key):
        return self.find_object_class(json_key, "mo_to_ldap")

    def find_mo_object_class(self, json_key):
        return self.find_object_class(json_key, "ldap_to_mo")

    def import_mo_object_class(self, json_key: str) -> type[MOBase]:
        return import_class(self.find_mo_object_class(json_key))

    def get_ldap_attributes(self, json_key, remove_dn=True):
        ldap_attributes = list(self.mapping["mo_to_ldap"][json_key].keys())
        if "dn" in ldap_attributes and remove_dn:
            # "dn" is the key which all LDAP objects have, not an attribute.
            ldap_attributes.remove("dn")
        return ldap_attributes

    def get_mo_attributes(self, json_key):
        return list(self.mapping["ldap_to_mo"][json_key].keys())

    def check_attributes(self, detected_attributes, accepted_attributes):
        problematic_attributes = {
            attribute
            for attribute in detected_attributes
            if (
                attribute not in accepted_attributes
                and not attribute.startswith("msDS-cloudExtensionAttribute")
                and not attribute.startswith("extensionAttribute")
                and not attribute.startswith("__")
            )
        }
        match self.settings.ldap_dialect:
            case "Standard":
                problematic_attributes.discard("entryUUID")
                problematic_attributes.discard("sn")
            case "AD":
                problematic_attributes.discard("sAMAccountName")
            case _:  # pragma: no cover
                raise AssertionError(
                    f"Unknown LDAP dialect: {self.settings.ldap_dialect}"
                )

        exceptions = [
            IncorrectMapping(f"Attribute '{attribute}' not allowed.")
            for attribute in problematic_attributes
        ]
        if exceptions:
            raise ExceptionGroup(
                f"check_attributes failed, allowed attributes are {accepted_attributes}",
                exceptions,
            )

    def get_json_keys(self, conversion):
        try:
            return list(self.mapping[conversion].keys())
        except KeyError as error:  # pragma: no cover
            # NOTE: We are not testing this as we intend to remove it
            raise IncorrectMapping(f"Missing key: '{conversion}'") from error

    def get_ldap_to_mo_json_keys(self):
        return self.get_json_keys("ldap_to_mo")

    def get_mo_to_ldap_json_keys(self):
        return self.get_json_keys("mo_to_ldap")

    def get_required_attributes(self, mo_class):
        if "required" in mo_class.schema():
            return mo_class.schema()["required"]
        return []

    @staticmethod
    def clean_get_current_method_from_template_string(template_string):
        """
        Cleans all calls to the get_current_* methods from a template string
        """
        return re.sub(r"get_current[^)]*\)", "", template_string)

    async def check_ldap_attributes(
        self, overview, graphql_client: GraphQLClient
    ) -> None:
        mo_to_ldap_json_keys = self.get_mo_to_ldap_json_keys()

        address_results = await graphql_client.read_class_user_keys(
            ["employee_address_type", "org_unit_address_type"]
        )
        mo_address_type_user_keys = {
            result.current.user_key
            for result in address_results.objects
            if result.current
        }
        mo_it_system_user_keys = await get_itsystem_user_keys(
            self.dataloader.graphql_client
        )

        for json_key in mo_to_ldap_json_keys:
            logger.info("Checking mo_to_ldap JSON key", key=json_key)

            object_class = self.find_ldap_object_class(json_key)

            accepted_attributes = list(overview[object_class]["attributes"].keys())
            detected_attributes = self.get_ldap_attributes(json_key, remove_dn=False)

            self.check_attributes(detected_attributes, accepted_attributes + ["dn"])

            detected_single_value_attributes = [
                a
                for a in detected_attributes
                if a == "dn" or self.dataloader.single_value[a]
            ]

            # Check single value fields which map to MO address/it-user/... objects.
            # We like fields which map to these MO objects to be multi-value fields,
            # to avoid data being overwritten if two objects of the same type are
            # added in MO
            def filter_fields_to_check(fields_to_check, json_key):
                """
                A field only needs to be checked if we use information from LDAP in
                the 'ldap_to_mo' mapping. If we do not, we also do not need to make
                sure that we are writing information to LDAP for this field.
                """
                fields_with_ldap_reference = []
                for field in fields_to_check:
                    mo_field = field.split(".")[1]
                    template = self.clean_get_current_method_from_template_string(
                        self.raw_mapping["ldap_to_mo"][json_key][mo_field]
                    )
                    if "ldap." in template:
                        fields_with_ldap_reference.append(field)

                return fields_with_ldap_reference

            fields_to_check = []
            if json_key in mo_address_type_user_keys:
                fields_to_check = filter_fields_to_check(
                    ["mo_employee_address.value"], json_key
                )
            elif json_key in mo_it_system_user_keys:
                fields_to_check = filter_fields_to_check(
                    ["mo_employee_it_user.user_key"], json_key
                )
            elif json_key == "Engagement":
                fields_to_check = filter_fields_to_check(
                    [
                        "mo_employee_engagement.user_key",
                        "mo_employee_engagement.org_unit.uuid",
                        "mo_employee_engagement.engagement_type.uuid",
                        "mo_employee_engagement.job_function.uuid",
                    ],
                    json_key,
                )

            for attribute in detected_single_value_attributes:
                template = self.raw_mapping["mo_to_ldap"][json_key][attribute]
                for field_to_check in fields_to_check:
                    if field_to_check in template:
                        logger.warning(
                            (
                                "LDAP attribute cannot contain multiple values. "
                                "Values in LDAP will be overwritten if multiple objects of the same type are added in MO."
                            ),
                            object_class=object_class,
                            attribute=attribute,
                            json_key=json_key,
                        )

            # Make sure that all attributes are single-value or multi-value. Not a mix.
            if len(fields_to_check) > 1:
                matching_attributes = []
                for field_to_check in fields_to_check:
                    for attribute in detected_attributes:
                        template = self.raw_mapping["mo_to_ldap"][json_key][attribute]
                        if field_to_check in template:
                            matching_attributes.append(attribute)
                            break

                if len(matching_attributes) != len(fields_to_check):
                    raise IncorrectMapping(
                        "Could not find all attributes belonging to "
                        f"{fields_to_check}. Only found the following "
                        f"attributes: {matching_attributes}."
                    )

                matching_single_value_attributes = [
                    a
                    for a in matching_attributes
                    if a in detected_single_value_attributes
                ]
                matching_multi_value_attributes = [
                    a
                    for a in matching_attributes
                    if a not in detected_single_value_attributes
                ]

                if len(matching_single_value_attributes) not in [
                    0,
                    len(fields_to_check),
                ]:
                    raise IncorrectMapping(
                        f"LDAP Attributes mapping to '{json_key}' are a mix "
                        "of multi- and single-value. The following attributes are "
                        f"single-value: {matching_single_value_attributes} "
                        "while the following are multi-value attributes: "
                        f"{matching_multi_value_attributes}"
                    )

                if (
                    json_key == "Engagement"
                    and len(matching_multi_value_attributes) > 0
                ):
                    raise IncorrectMapping(
                        f"LDAP Attributes mapping to 'Engagement' contain one or "
                        f"more multi-value attributes "
                        f"{matching_multi_value_attributes}, which is not allowed"
                    )

    def check_ldap_to_mo_references(self, overview):
        # https://ff1959.wordpress.com/2012/03/04/characters-that-are-permitted-in-
        # attribute-names-descriptors/
        # The only characters that are permitted in attribute names are ALPHA, DIGIT,
        # and HYPHEN (‘-’). Underscores ‘_’ are not permitted.
        valid_chars = string.ascii_letters + string.digits + "-"
        invalid_chars = "".join([s for s in string.punctuation if s not in valid_chars])
        invalid_chars_regex = rf"[{invalid_chars}\s]\s*"

        raw_mapping = self.raw_mapping["ldap_to_mo"]
        for json_key in self.get_ldap_to_mo_json_keys():
            object_class = self.find_ldap_object_class(json_key)
            accepted_attributes = sorted(
                list(overview[object_class]["attributes"].keys()) + ["dn"]
            )
            for value in raw_mapping[json_key].values():
                if not isinstance(value, str):
                    continue
                if "ldap." in value:
                    ldap_refs = value.split("ldap.")[1:]

                    for ldap_ref in ldap_refs:
                        ldap_attribute = re.split(invalid_chars_regex, ldap_ref)[0]
                        self.check_attributes([ldap_attribute], accepted_attributes)

    def check_cpr_field_or_it_system(self):
        """
        Check that we have either a cpr-field OR an it-system which maps to an LDAP DN
        """
        if not self.cpr_field and not self.ldap_it_system:
            raise IncorrectMapping(
                "Neither a cpr-field or an ldap it-system could be found"
            )

    async def check_mapping(self, mapping: dict[str, Any]) -> None:
        """Check if the configured mapping is valid.

        Args:
            mapping: The raw mapping configuration.

        Raises:
            IncorrectMapping: Raised if the mapping is invalid.
        """

        logger.info("Checking json file")

        overview = self.dataloader.load_ldap_overview()

        # check that the LDAP attributes match what is available in LDAP
        await self.check_ldap_attributes(overview, self.dataloader.graphql_client)

        # Check that fields referred to in ldap_to_mo actually exist in LDAP
        self.check_ldap_to_mo_references(overview)

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
            mapping = self.mapping["mo_to_ldap"]
        except KeyError as error:
            raise IncorrectMapping("Missing mapping 'mo_to_ldap'") from error
        try:
            object_mapping = mapping[json_key]
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
                mapping = self.mapping["ldap_to_mo"]
            except KeyError as error:
                raise IncorrectMapping("Missing mapping 'ldap_to_mo'") from error
            try:
                object_mapping = mapping[json_key]
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
            mo_class = self.import_mo_object_class(json_key)
            required_attributes = set(self.get_required_attributes(mo_class))

            # Load our validity default, if it is not set
            missing_attributes = required_attributes - set(mo_dict.keys())
            # TODO: Once validity has been removed from the config
            #       Replace this 'if' with an assert instead
            if "validity" in missing_attributes:
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
