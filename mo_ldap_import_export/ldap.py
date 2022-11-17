# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
"""LDAP Connection handling."""
from ssl import CERT_NONE
from ssl import CERT_REQUIRED
from typing import cast
from typing import ContextManager
from typing import Union

import structlog
from fastramqpi.context import Context
from ldap3 import Connection
from ldap3 import NTLM
from ldap3 import RANDOM
from ldap3 import RESTARTABLE
from ldap3 import Server
from ldap3 import ServerPool
from ldap3 import Tls
from more_itertools import always_iterable
from more_itertools import only

from .config import ServerConfig
from .config import Settings


def construct_server(server_config: ServerConfig) -> Server:
    """Construct an LDAP3 server from settings.

    Args:
        server_config: The settings to construct the server instance from.

    Returns:
        The constructed server instance used for LDAP connections.
    """
    tls_configuration = Tls(
        validate=CERT_NONE if server_config.insecure else CERT_REQUIRED
    )

    logger = structlog.get_logger()
    logger.info("Setting up server to %s" % server_config.host)
    return Server(
        host=server_config.host,
        port=server_config.port,
        use_ssl=server_config.use_ssl,
        tls=tls_configuration,
        connect_timeout=server_config.timeout,
    )


def get_client_strategy():
    return RESTARTABLE


def configure_ldap_connection(settings: Settings) -> ContextManager:
    """Configure an LDAP connection.

    Args:
        settings: The Settings instance to configure our ad connection with.

    Returns:
        ContextManager that can be opened to establish an LDAP connection.
    """
    servers = list(map(construct_server, settings.ldap_controllers))

    # Pick the next server to use at random, discard non-active servers
    server_pool = ServerPool(servers, RANDOM, active=True, exhaust=True)

    logger = structlog.get_logger()
    logger.info("Connecting to %s" % server_pool)
    logger.info("Client strategy: %s" % get_client_strategy())
    connection = Connection(
        server=server_pool,
        user=settings.ldap_domain + "\\" + settings.ldap_user,
        password=settings.ldap_password.get_secret_value(),
        authentication=NTLM,
        client_strategy=get_client_strategy(),
        auto_bind=True,
    )

    return cast(ContextManager, connection)


async def ldap_healthcheck(context: Union[dict, Context]) -> bool:
    """LDAP connection Healthcheck.

    Args:
        context: To lookup ldap_connection in.

    Returns:
        Whether the AMQPSystem is OK.
    """
    ldap_connection = context["user_context"]["ldap_connection"]
    return cast(bool, ldap_connection.bound)


def get_ldap_schema(ldap_connection):
    return ldap_connection.server.schema


def get_ldap_object_schema(ldap_connection, ldap_object: str):
    schema = get_ldap_schema(ldap_connection)
    return schema.object_classes[ldap_object]


def get_ldap_superiors(ldap_connection, ldap_object: Union[str, None]):

    superiors = []
    while ldap_object is not None:
        schema = get_ldap_object_schema(ldap_connection, ldap_object)
        ldap_object = only(always_iterable(schema.superior))
        if ldap_object is not None:
            superiors.append(ldap_object)

    return superiors


def get_ldap_attributes(ldap_connection, root_ldap_object: Union[str, None]):
    """
    ldap_connection : ldap connection object
    ldap_object : ldap class to fetch attributes for. for example "organizationalPerson"
    """

    logger = structlog.get_logger()
    all_attributes = []
    superiors = get_ldap_superiors(ldap_connection, root_ldap_object)

    for ldap_object in [root_ldap_object] + superiors:
        schema = get_ldap_object_schema(ldap_connection, ldap_object)
        if ldap_object != "top":
            logger.info("Fetching allowed objects for %s" % ldap_object)
            all_attributes += schema.may_contain
    return all_attributes


def paged_search(context: Context, searchParameters: dict) -> list:
    """
    searchParameters : dict
        Dict with the following keys:
            * search_filter
            * attributes
    """
    responses = []
    logger = structlog.get_logger()

    user_context = context["user_context"]
    search_base = user_context["settings"].ldap_search_base
    ldap_connection = user_context["ldap_connection"]

    # TODO: Find max. paged_size number from LDAP rather than hard-code it?
    searchParameters["paged_size"] = 500
    searchParameters["search_base"] = search_base

    logger.info(
        "searching for %s on %s"
        % (searchParameters["search_filter"], searchParameters["search_base"])
    )

    # Max 10_000 pages to avoid eternal loops
    for page in range(0, 10_000):
        logger.info("searching page %d" % page)
        ldap_connection.search(**searchParameters)

        if ldap_connection.result["description"] == "operationsError":
            logger.warn("%s Search failed" % searchParameters["search_filter"])
            break

        entries = [r for r in ldap_connection.response if r["type"] == "searchResEntry"]
        responses.extend(entries)

        # TODO: Skal "1.2.840.113556.1.4.319" være Configurerbar?
        cookie = ldap_connection.result["controls"]["1.2.840.113556.1.4.319"]["value"][
            "cookie"
        ]

        if cookie and type(cookie) is bytes:
            searchParameters["paged_cookie"] = cookie
        else:
            break

    return responses
