# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
# pylint: disable=too-few-public-methods
"""Settings handling."""
from fastramqpi.config import Settings as FastRAMQPISettings
from pydantic import AmqpDsn
from pydantic import AnyHttpUrl
from pydantic import BaseModel
from pydantic import BaseSettings
from pydantic import ConstrainedList
from pydantic import Field
from pydantic import parse_obj_as
from pydantic import SecretStr
from ramqp.config import ConnectionSettings as AMQPConnectionSettings


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
    insecure: bool = Field(False, description="Whether to verify SSL certificates")
    timeout: int = Field(5, description="Number of seconds to wait for connection")


class ServerList(ConstrainedList):
    """Constrainted list for domain controllers."""

    min_items = 1
    unique_items = True

    item_type = ServerConfig
    __args__ = (ServerConfig,)


class InternalAMQPConnectionSettings(AMQPConnectionSettings):
    exchange = "ldap_ie"
    queue_prefix = "ldap_ie"
    prefetch_count = 1  # MO cannot handle too many requests
    url: AmqpDsn = parse_obj_as(AmqpDsn, "amqp://guest:guest@msg_broker")


class Settings(BaseSettings):
    class Config:
        frozen = True
        env_nested_delimiter = "__"

    internal_amqp: InternalAMQPConnectionSettings = Field(
        default_factory=InternalAMQPConnectionSettings,
        description="Internal amqp settings",
    )

    fastramqpi: FastRAMQPISettings = Field(
        default_factory=FastRAMQPISettings, description="FastRAMQPI settings"
    )

    amqp_url: AmqpDsn = parse_obj_as(AmqpDsn, "amqp://guest:guest@msg_broker")
    amqp_exchange: str = "os2mo"
    listen_to_changes_in_mo: bool = Field(
        True, description="Whether to write to AD, when changes in MO are registered"
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

    mo_url: AnyHttpUrl = Field(
        parse_obj_as(AnyHttpUrl, "http://mo-service:5000"),
        description="Base URL for OS2mo.",
    )

    client_id: str = Field("bruce", description="Client ID for OIDC client.")
    client_secret: SecretStr = Field(..., description="Client Secret for OIDC client.")
    auth_server: AnyHttpUrl = Field(
        parse_obj_as(AnyHttpUrl, "http://keycloak-service:8080/auth"),
        description="Base URL for OIDC server (Keycloak).",
    )
    auth_realm: str = Field("mo", description="Realm to authenticate against")

    graphql_timeout: int = 120

    admin_password: SecretStr = Field(
        ...,
        description="Password to use when authenticating to FastAPI docs",
    )
    authentication_secret: SecretStr = Field(
        ...,
        description="secret key for FastAPI docs login manager",
    )

    default_org_unit_type: str = Field(
        ..., description="Type to set onto imported organization units"
    )

    default_org_unit_level: str = Field(
        ..., description="Level to set onto imported organization units"
    )

    token_expiry_time: float = Field(
        8, description="Time in hours until a FastAPI auth token expires"
    )

    org_unit_path_string_separator: str = Field(
        "//", description="separator for full paths to org units in LDAP"
    )

    poll_time: float = Field(
        5, description="Time between calls to LDAP to search for updates"
    )
