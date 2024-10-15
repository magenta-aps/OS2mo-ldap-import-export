# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
# pylint: disable=too-few-public-methods
"""Settings handling."""

from contextlib import suppress
from enum import Enum
from typing import Any
from typing import Literal
from typing import get_args

import structlog
from fastramqpi.config import Settings as FastRAMQPISettings
from fastramqpi.ramqp.config import AMQPConnectionSettings
from fastramqpi.ramqp.utils import RequeueMessage
from more_itertools import duplicates_everseen
from more_itertools import flatten
from pydantic import AnyHttpUrl
from pydantic import BaseModel
from pydantic import BaseSettings
from pydantic import ConstrainedList
from pydantic import Extra
from pydantic import Field
from pydantic import SecretStr
from pydantic import parse_obj_as
from pydantic import root_validator
from pydantic import validator
from ramodels.mo import MOBase
from ramodels.mo.detail import Detail

from .utils import import_class

logger = structlog.stdlib.get_logger()


def value_or_default(dicty: dict[str, Any], key: str, default: Any) -> None:
    dicty[key] = dicty.get(key) or default


class ServerConfig(BaseModel):
    """Settings model for domain controllers."""

    class Config:
        """Settings are frozen."""

        frozen = True

    host: str = Field(..., description="Hostname / IP to establish connection with")
    port: int | None = Field(
        None,
        description=(
            "Port to utilize when establishing a connection. Defaults to 636 for SSL"
            " and 389 for non-SSL"
        ),
    )
    use_ssl: bool = Field(False, description="Whether to establish a SSL connection")
    ca_certs_data: str | None = Field(
        None, description="The CA chain to verify SSL with"
    )
    insecure: bool = Field(False, description="Whether to verify SSL certificates")
    timeout: int = Field(5, description="Number of seconds to wait for connection")


class ServerList(ConstrainedList):
    """Constrainted list for domain controllers."""

    min_items = 1
    unique_items = True

    item_type = ServerConfig
    __args__ = (ServerConfig,)


class LDAPAMQPConnectionSettings(AMQPConnectionSettings):
    exchange = "ldap_ie_ldap"
    queue_prefix = "ldap_ie_ldap"
    prefetch_count = 1  # MO cannot handle too many requests


class ExternalAMQPConnectionSettings(AMQPConnectionSettings):
    queue_prefix = "ldap_ie"
    upstream_exchange = "os2mo"
    prefetch_count: int = 1  # MO cannot handle too many requests

    @root_validator
    def set_exchange_by_queue_prefix(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Ensure that exchange is set based on queue_prefix."""
        values["exchange"] = "os2mo_" + values["queue_prefix"]
        return values


class FastFAMQPIApplicationSettings(FastRAMQPISettings):
    amqp: ExternalAMQPConnectionSettings


class MappingBaseModel(BaseModel):
    class Config:
        frozen = True
        extra = Extra.forbid


def get_required_attributes(mo_class) -> set[str]:
    if "required" not in mo_class.schema():
        return set()
    return set(mo_class.schema()["required"])


class LDAP2MOMapping(MappingBaseModel):
    class Config:
        extra = Extra.allow

    objectClass: str
    import_to_mo: Literal["true", "false", "manual_import_only"] = Field(
        alias="_import_to_mo_"
    )
    terminate: str | None = Field(
        alias="_terminate_", description="The date at which to terminate the object"
    )
    mapper: str | None = Field(
        None,
        alias="_mapper_",
        description="Jinja template for mapping between LDAP and MO objects",
    )
    ldap_attributes: list[str] = Field(
        ...,
        alias="_ldap_attributes_",
        description="The attributes to fetch for LDAP, aka attributes available on the ldap object in templates",
    )

    def import_to_mo_as_bool(self, manual_import: bool = False) -> bool:
        """
        Returns True, when we need to import this object. Otherwise False
        """
        import_flag = self.import_to_mo.lower()

        match import_flag:
            case "true":
                return True
            case "manual_import_only":
                return manual_import
            case "false":
                return False
            case _:  # pragma: no cover
                raise AssertionError(f"Import flag = '{import_flag}' not recognized")

    def as_mo_class(self) -> type[MOBase]:
        return import_class(self.objectClass)

    @validator("import_to_mo", pre=True)
    def lower_import_to_mo(cls, v: str) -> str:
        return v.lower()

    @root_validator
    def check_terminate_only_set_on_valid_type(
        cls, values: dict[str, Any]
    ) -> dict[str, Any]:
        """Ensure that terminate is only set on things we can terminate."""
        if not values["terminate"]:
            return values

        # model_type is a name like 'address', 'engagement' or 'it'
        mo_class = import_class(values["objectClass"])
        model_type = mo_class.__fields__["type_"].default

        # The detail type contains a literal with valid details that can be terminated
        # To extract the strings given in the literal we use get_args
        detail_type = Detail.__fields__["type"].type_
        terminatable_model_types = get_args(detail_type)

        if model_type not in terminatable_model_types:
            raise ValueError(f"Termination not supported for {mo_class}")

        return values

    @root_validator
    def check_uuid_refs_in_mo_objects(cls, values: dict[str, Any]) -> dict[str, Any]:
        # Check that MO objects have a uuid field
        mo_class = import_class(values["objectClass"])

        properties = mo_class.schema()["properties"]
        # If we are dealing with an object that links to a person/org_unit
        # TODO: Add `or "org_unit" in properties`?
        if "person" in properties:
            # Either person or org_unit needs to be set
            has_person = "person" in values
            has_org_unit = "org_unit" in values
            if not has_person and not has_org_unit:
                raise ValueError(
                    "Either 'person' or 'org_unit' key needs to be present"
                )

            # Sometimes only one of them can be set
            required_attributes = get_required_attributes(mo_class)
            requires_person = "person" in required_attributes
            requires_org_unit = "org_unit" in required_attributes
            requires_both = requires_person and requires_org_unit
            if has_person and has_org_unit and not requires_both:
                raise ValueError(
                    "Either 'person' or 'org_unit' key needs to be present. Not both"
                )

            # TODO: What if both are required?
            uuid_key = "person" if "person" in values else "org_unit"
            # And the corresponding item needs to be a dict with an uuid key
            if "dict(uuid=" not in values[uuid_key].replace(" ", ""):
                raise ValueError("Needs to be a dict with 'uuid' as one of its keys")
        # Otherwise: We are dealing with the org_unit/person itself.
        else:
            # A field called 'uuid' needs to be present
            if "uuid" not in values:
                raise ValueError("Needs to contain a key called 'uuid'")
            # And it needs to contain a reference to the employee_uuid global
            if "employee_uuid" not in values["uuid"]:
                raise ValueError("Needs to contain a reference to 'employee_uuid'")
        return values

    @root_validator
    def check_mo_attributes(cls, values: dict[str, Any]) -> dict[str, Any]:
        mo_class = import_class(values["objectClass"])

        accepted_attributes = set(mo_class.schema()["properties"].keys())
        detected_attributes = set(values.keys()) - {
            "objectClass",
            "import_to_mo",
            "terminate",
            "mapper",
            "ldap_attributes",
        }
        # Disallow validity until we introduce a consistent behavior in the future
        if "validity" in detected_attributes:
            raise ValueError("'validity' cannot be set on the ldap_to_mo mapping")

        superfluous_attributes = detected_attributes - accepted_attributes
        if superfluous_attributes:
            raise ValueError(
                f"Attributes {superfluous_attributes} are not allowed. "
                f"The following attributes are allowed: {accepted_attributes}"
            )

        required_attributes = get_required_attributes(mo_class)
        if values["objectClass"] == "ramodels.mo.details.engagement.Engagement":
            # We require a primary attribute. If primary is not desired you can set
            # it to {{ NONE }} in the json dict
            required_attributes.add("primary")

        # Validity is no longer required, as we default to last midnight
        required_attributes.discard("validity")

        missing_attributes = required_attributes - detected_attributes
        if missing_attributes:
            raise ValueError(
                f"Missing {missing_attributes} which are mandatory. "
                f"The following attributes are mandatory: {required_attributes}"
            )
        return values


class MO2LDAPMapping(MappingBaseModel):
    class Config:
        extra = Extra.allow

    export_to_ldap: Literal["true", "false", "pause"] = Field(alias="_export_to_ldap_")

    def export_to_ldap_as_bool(self) -> bool:
        """
        Returns True, when we need to export this object. Otherwise False
        """
        export_flag = self.export_to_ldap.lower()

        match export_flag:
            case "true":
                return True
            case "false":
                return False
            case "pause":
                logger.info("_export_to_ldap_ = 'pause'. Requeueing.")
                raise RequeueMessage("Export paused, requeueing")
            case _:  # pragma: no cover
                raise AssertionError(f"Export flag = '{export_flag}' not recognized")

    @validator("export_to_ldap", pre=True)
    def lower_export_to_ldap(cls, v: str) -> str:
        return v.lower()


class UsernameGeneratorConfig(MappingBaseModel):
    objectClass: str = "UserNameGenerator"
    char_replacement: dict[str, str] = {}
    forbidden_usernames: list[str] = []
    combinations_to_try: list[str] = []

    @validator("forbidden_usernames")
    def casefold_forbidden_usernames(cls, v: list[str]) -> list[str]:
        return [u.casefold() for u in v]

    @validator("combinations_to_try")
    def check_combinations(cls, v: list[str]) -> list[str]:
        # Validator for combinations_to_try
        accepted_characters = ["F", "L", "1", "2", "3", "X"]
        for combination in v:
            if not all([c in accepted_characters for c in combination]):
                raise ValueError(
                    f"Incorrect combination found: '{combination}' username "
                    f"combinations can only contain {accepted_characters}"
                )
        return v


class ConversionMapping(MappingBaseModel):
    ldap_to_mo: dict[str, LDAP2MOMapping]
    mo_to_ldap: dict[str, MO2LDAPMapping]
    mo2ldap: str | None = Field(None, description="MO to LDAP mapping template")
    username_generator: UsernameGeneratorConfig = Field(
        default_factory=UsernameGeneratorConfig
    )

    @validator("mo_to_ldap")
    def check_for_conflicts(
        cls, v: dict[str, MO2LDAPMapping]
    ) -> dict[str, MO2LDAPMapping]:
        """Check that no mo_to_ldap mappings map the same fields."""
        mappings = [mapping.dict().keys() for mapping in v.values()]
        conflicts = set(duplicates_everseen(flatten(mappings)))
        # Allow multiple configs to have these keys as they are required for each
        conflicts -= {"objectClass", "export_to_ldap"}
        if conflicts:
            raise ValueError(f"Conflicting fields in 'mo_to_ldap' mapping: {conflicts}")
        return v


class AuthBackendEnum(str, Enum):
    NTLM = "ntlm"
    SIMPLE = "simple"


class Settings(BaseSettings):
    class Config:
        frozen = True
        env_nested_delimiter = "__"

        env_file = "/var/run/.env"
        env_file_encoding = "utf-8"

    conversion_mapping: ConversionMapping = Field(
        description="Conversion mapping between LDAP and OS2mo",
    )

    ldap_amqp: LDAPAMQPConnectionSettings = Field(
        default_factory=LDAPAMQPConnectionSettings,  # type: ignore
        description="LDAP amqp settings",
    )

    fastramqpi: FastFAMQPIApplicationSettings

    @root_validator(pre=True)
    def share_amqp_url(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Use FastRAMQPI__AMQP__URL as a default for AMQP URLs"""
        # If a key-error occurs, do nothing and let the validation explain it
        with suppress(KeyError):
            fastramqpi_amqp_url = values["fastramqpi"]["amqp"]["url"]

            values["ldap_amqp"] = values.get("ldap_amqp", {})
            values["ldap_amqp"]["url"] = values["ldap_amqp"].get(
                "url", fastramqpi_amqp_url
            )
        return values

    listen_to_changes_in_mo: bool = Field(
        True, description="Whether to write to AD, when changes in MO are registered"
    )

    listen_to_changes_in_ldap: bool = Field(
        True, description="Whether to write to MO, when changes in LDAP are registered"
    )

    add_objects_to_ldap: bool = Field(
        True,
        description=(
            "If True: Adds new objects to LDAP "
            "when an object is in MO but not in LDAP. "
            "If False: Only modifies existing objects."
        ),
    )

    ldap_controllers: ServerList = Field(
        ..., description="List of domain controllers to query"
    )
    ldap_domain: str = Field(
        ..., description="Domain to use when authenticating with the domain controller"
    )
    ldap_user: str = Field(
        "os2mo",
        description="Username to use when authenticating with the domain controller",
    )
    ldap_password: SecretStr = Field(
        ...,
        description="Password to use when authenticating with the domain controller",
    )
    ldap_search_base: str = Field(
        ..., description="Search base to utilize for all LDAP requests"
    )

    ldap_object_class: str = Field(
        ..., description="The LDAP object class that contains the CPR number"
    )
    ldap_cpr_attribute: str | None = Field(
        None,
        description="The attribute (if any) that contains the CPR number in LDAP",
    )
    ldap_it_system: str | None = Field(
        None,
        description="The user-key (if any) of the ADGUID IT-system in MO",
    )

    @root_validator
    def check_ldap_correlation_key(cls, values: dict[str, Any]) -> dict[str, Any]:
        if values["ldap_cpr_attribute"] is None and values["ldap_it_system"] is None:
            raise ValueError(
                "'LDAP_CPR_ATTRIBUTE' and 'LDAP_IT_SYSTEM' cannot both be 'None'. "
                "Atleast one must be set to allow for MO<-->LDAP correlation."
            )
        return values

    ldap_ous_to_search_in: list[str] = Field(
        [""],
        description=(
            "List of OUs to search in. If this contains an empty string; "
            "Searches in all OUs in the search base"
        ),
    )
    ldap_ous_to_write_to: list[str] = Field(
        [""],
        description=(
            "List of OUs to write to. If this contains an empty string; "
            "Writes to all OUs in the search base"
        ),
    )
    ldap_ou_for_new_users: str = Field(
        "", description="OU to create new users in. For example 'OU=Test'"
    )
    ldap_auth_method: AuthBackendEnum = Field(
        AuthBackendEnum.NTLM, description="The auth backend to use."
    )
    ldap_dialect: Literal["Standard", "AD"] = Field(
        "AD", description="Which LDAP dialect to use"
    )
    ldap_unique_id_field: str = Field(
        "",
        description="Name of the attribute that holds the server-assigned unique identifier. `objectGUID` on Active Directory and `entryUUID` on most standard LDAP implementations (per RFC4530).",
    )
    ldap_user_objectclass: str = Field("", description="Object class for users")

    @root_validator
    def set_dialect_defaults(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Root-validator to set LDAP dialect specific defaults.

        This validator exists to ease the configuration of the component if one uses a
        one of the supported LDAP dialects.
        """
        dialect = values.get("ldap_dialect", "UNKNOWN")
        if dialect == "Standard":
            value_or_default(values, "ldap_unique_id_field", "entryUUID")
            value_or_default(values, "ldap_user_objectclass", "inetOrgPerson")
        if dialect == "AD":
            value_or_default(values, "ldap_unique_id_field", "objectGUID")
            value_or_default(values, "ldap_user_objectclass", "user")
        return values

    # NOTE: It appears that this flag does not in fact work
    # See: https://github.com/cannatag/ldap3/issues/1008
    ldap_read_only: bool = Field(
        False, description="Whether to establish a read-only connection to the server."
    )
    ldap_receive_timeout: int = Field(
        10, description="Number of seconds to wait for communication (wire timeout)."
    )
    ldap_response_timeout: int = Field(
        10, description="Number of seconds to wait for responses (query timeout)."
    )

    # TODO: Remove this, as it already exists within FastRAMQPI?
    mo_url: AnyHttpUrl = Field(
        parse_obj_as(AnyHttpUrl, "http://mo-service:5000"),
        description="Base URL for OS2mo.",
    )

    default_org_unit_type: str = Field(
        ..., description="Type to set onto imported organization units"
    )

    default_org_unit_level: str = Field(
        ..., description="Level to set onto imported organization units"
    )

    org_unit_path_string_separator: str = Field(
        "\\", description="separator for full paths to org units in LDAP"
    )

    poll_time: float = Field(
        5, description="Seconds between calls to LDAP to search for updates"
    )

    it_user_to_check: str = Field(
        "",
        description=(
            "Check that an employee has an it-user with this user_key "
            "before writing to LDAP"
        ),
    )

    check_holstebro_ou_issue_57426: list[str] = Field(
        [],
        description="Check that OU is below or equal one of these, see #57426",
    )

    discriminator_field: str | None = Field(
        None, description="The field to look for discriminator values in"
    )

    discriminator_function: Literal["exclude", "include", "template", None] = Field(
        None,
        description="The type of discriminator function, either exclude, include or template",
    )

    discriminator_values: list[str] = Field(
        [], description="The values used for discrimination"
    )

    @root_validator
    def check_discriminator_settings(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Ensure that discriminator function and values is set, if field is set."""
        # No discriminator_field, not required fields
        if values["discriminator_field"] is None:
            return values
        # If our keys are not in values, a field validator failed, let it handle it
        if (
            "discriminator_function" not in values
            or "discriminator_values" not in values
        ):
            return values
        # Check that our now required fields are set
        if values["discriminator_function"] is None:
            raise ValueError(
                "DISCRIMINATOR_FUNCTION must be set, if DISCRIMINATOR_FIELD is set"
            )
        if values["discriminator_values"] == []:
            raise ValueError(
                "DISCRIMINATOR_VALUES must be set, if DISCRIMINATOR_FIELD is set"
            )
        return values
