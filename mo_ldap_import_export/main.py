# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
"""Event handling."""
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any

import structlog
from fastapi import APIRouter
from fastapi import Depends
from fastapi import FastAPI
from fastramqpi.main import FastRAMQPI
from fastramqpi.ramqp.depends import rate_limit
from fastramqpi.ramqp.mo import MORouter
from fastramqpi.ramqp.mo import PayloadUUID
from fastramqpi.ramqp.utils import RejectMessage
from fastramqpi.ramqp.utils import RequeueMessage
from gql.transport.exceptions import TransportQueryError
from ldap3 import Connection
from more_itertools import one

from . import depends
from .autogenerated_graphql_client import GraphQLClient
from .config import Settings
from .converters import LdapConverter
from .customer_specific_checks import ExportChecks
from .customer_specific_checks import ImportChecks
from .dataloaders import DataLoader
from .exceptions import IgnoreChanges
from .exceptions import IncorrectMapping
from .exceptions import NoObjectsReturnedException
from .exceptions import NotEnabledException
from .exceptions import NotSupportedException
from .import_export import SyncTool
from .ldap import check_ou_in_list_of_ous
from .ldap import configure_ldap_connection
from .ldap import ldap_healthcheck
from .ldap import poller_healthcheck
from .ldap import setup_listener
from .ldap_amqp import configure_ldap_amqpsystem
from .logging import init as initialize_logging
from .os2mo_init import InitEngine
from .routes import construct_router
from .types import OrgUnitUUID
from .usernames import get_username_generator_class

logger = structlog.stdlib.get_logger()

fastapi_router = APIRouter()
amqp_router = MORouter()
delay_on_error = 10  # Try errors again after a short period of time
delay_on_requeue = 60 * 60 * 24  # Requeue messages for tomorrow (or after a reboot)


def reject_on_failure(func):
    """
    Decorator to turn message into dead letter in case of exceptions.
    """

    @wraps(func)
    async def modified_func(*args, **kwargs):
        try:
            await func(*args, **kwargs)
        except RejectMessage as e:  # In case we explicitly reject the message: Abort
            logger.info(e)
            raise
        except (
            NotSupportedException,  # For features that are not supported: Abort
            IncorrectMapping,  # If the json dict is incorrectly configured: Abort
            TransportQueryError,  # In case an ldap entry cannot be uploaded: Abort
            NoObjectsReturnedException,  # In case an object is deleted halfway: Abort
            IgnoreChanges,  # In case changes should be ignored: Abort
            NotEnabledException,  # In case a feature is not enabled: Abort
        ) as e:
            logger.info(e)
            raise RejectMessage() from e
        except RequeueMessage:
            await asyncio.sleep(delay_on_requeue)
            raise

    modified_func.__wrapped__ = func  # type: ignore
    return modified_func


@amqp_router.register("address")
@reject_on_failure
async def process_address(
    object_uuid: PayloadUUID,
    graphql_client: depends.GraphQLClient,
    amqpsystem: depends.AMQPSystem,
) -> None:
    result = await graphql_client.read_address_relation_uuids(object_uuid)
    try:
        obj = one(result.objects)
    except ValueError:
        logger.warning("Unable to lookup address", uuid=object_uuid)
        raise RejectMessage("Unable to lookup address")

    if obj.current is None:
        logger.warning("Address not currently active", uuid=object_uuid)
        raise RejectMessage("Address not currently active")

    person_uuid = obj.current.employee_uuid
    org_unit_uuid = obj.current.org_unit_uuid

    if person_uuid is not None:
        # TODO: Add support for refreshing persons with a certain address directly
        await graphql_client.employee_refresh(amqpsystem.exchange_name, [person_uuid])
    if org_unit_uuid is not None:
        # TODO: Should really only be primary engagement relations
        e_result = await graphql_client.read_employees_with_engagement_to_org_unit(
            org_unit_uuid
        )
        employee_uuids = {
            x.current.employee_uuid for x in e_result.objects if x.current is not None
        }
        # TODO: Add support for refreshing persons with a primary engagement relation directly
        await graphql_client.employee_refresh(
            amqpsystem.exchange_name, list(employee_uuids)
        )


@amqp_router.register("engagement")
@reject_on_failure
async def process_engagement(
    object_uuid: PayloadUUID,
    graphql_client: depends.GraphQLClient,
    amqpsystem: depends.AMQPSystem,
) -> None:
    result = await graphql_client.read_engagement_employee_uuid(object_uuid)
    try:
        obj = one(result.objects)
    except ValueError:
        logger.warning("Unable to lookup engagement", uuid=object_uuid)
        raise RejectMessage("Unable to lookup engagement")

    if obj.current is None:
        logger.warning("Engagement not currently active", uuid=object_uuid)
        raise RejectMessage("Engagement not currently active")

    person_uuid = obj.current.employee_uuid
    # TODO: Add support for refreshing persons with a certain engagement directly
    await graphql_client.employee_refresh(amqpsystem.exchange_name, [person_uuid])


@amqp_router.register("ituser")
@reject_on_failure
async def process_ituser(
    object_uuid: PayloadUUID,
    graphql_client: depends.GraphQLClient,
    amqpsystem: depends.AMQPSystem,
) -> None:
    result = await graphql_client.read_ituser_employee_uuid(object_uuid)
    try:
        obj = one(result.objects)
    except ValueError:
        logger.warning("Unable to lookup ITUser", uuid=object_uuid)
        raise RejectMessage("Unable to lookup ITUser")

    if obj.current is None:
        logger.warning("ITUser not currently active", uuid=object_uuid)
        raise RejectMessage("ITUser not currently active")

    person_uuid = obj.current.employee_uuid
    if person_uuid is None:
        logger.warning("ITUser not attached to a person", uuid=object_uuid)
        raise RejectMessage("ITUser not attached to a person")

    # TODO: Add support for refreshing persons with a certain ituser directly
    await graphql_client.employee_refresh(amqpsystem.exchange_name, [person_uuid])


@amqp_router.register("person")
@reject_on_failure
async def process_person(
    object_uuid: PayloadUUID,
    sync_tool: depends.SyncTool,
) -> None:
    await sync_tool.listen_to_changes_in_employees(object_uuid)


@amqp_router.register("org_unit")
@reject_on_failure
async def process_org_unit(
    object_uuid: PayloadUUID,
    sync_tool: depends.SyncTool,
) -> None:
    logger.info(
        "Registered change in an org_unit",
        object_uuid=object_uuid,
    )
    # In case the name of the org-unit changed, we need to publish an
    # "engagement" message for each of its employees. Because org-unit
    # LDAP mapping is primarily done through the "Engagement" json-key.
    await sync_tool.publish_engagements_for_org_unit(OrgUnitUUID(object_uuid))
    await sync_tool.refresh_org_unit_info_cache()


@asynccontextmanager
async def open_ldap_connection(ldap_connection: Connection) -> AsyncIterator[None]:
    """Open the LDAP connection during FastRAMQPI lifespan.

    Yields:
        None
    """
    with ldap_connection:
        yield


# https://fastapi.tiangolo.com/advanced/events/
@asynccontextmanager
async def initialize_sync_tool(fastramqpi: FastRAMQPI) -> AsyncIterator[None]:
    logger.info("Initializing Sync tool")
    sync_tool = SyncTool(fastramqpi.get_context())
    fastramqpi.add_context(sync_tool=sync_tool)
    yield


@asynccontextmanager
async def initialize_checks(fastramqpi: FastRAMQPI) -> AsyncIterator[None]:
    logger.info("Initializing Import/Export checks")
    export_checks = ExportChecks(fastramqpi.get_context())
    import_checks = ImportChecks(fastramqpi.get_context())
    fastramqpi.add_context(export_checks=export_checks, import_checks=import_checks)
    yield


@asynccontextmanager
async def initialize_converters(fastramqpi: FastRAMQPI) -> AsyncIterator[None]:
    logger.info("Initializing converters")
    converter = LdapConverter(fastramqpi.get_context())
    await converter._init()
    fastramqpi.add_context(cpr_field=converter.cpr_field)
    fastramqpi.add_context(ldap_it_system_user_key=converter.ldap_it_system)
    fastramqpi.add_context(converter=converter)
    yield


@asynccontextmanager
async def initialize_init_engine(fastramqpi: FastRAMQPI) -> AsyncIterator[None]:
    logger.info("Initializing os2mo-init engine")
    init_engine = InitEngine(fastramqpi.get_context())
    await init_engine.create_facets()
    await init_engine.create_it_systems()
    fastramqpi.add_context(init_engine=init_engine)
    yield


@asynccontextmanager
async def initialize_ldap_listener(fastramqpi: FastRAMQPI) -> AsyncIterator[None]:
    logger.info("Initializing LDAP listener")
    pollers = setup_listener(fastramqpi.get_context())
    fastramqpi.add_context(pollers=pollers)
    fastramqpi.add_healthcheck(name="LDAPPoller", healthcheck=poller_healthcheck)
    yield


# TODO: Eliminate this function and make reloading dicts eventdriven
@asynccontextmanager
async def initialize_info_dict_refresher(fastramqpi: FastRAMQPI) -> AsyncIterator[None]:
    async def refresher() -> None:
        user_context = fastramqpi._context["user_context"]
        converter = user_context["converter"]
        while True:
            await converter.load_info_dicts()
            await asyncio.sleep(24 * 60 * 60)

    task = asyncio.create_task(refresher())

    yield

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def create_fastramqpi(**kwargs: Any) -> FastRAMQPI:
    """FastRAMQPI factory.

    Returns:
        FastRAMQPI system.
    """
    logger.info("Retrieving settings")
    settings = Settings(**kwargs)

    initialize_logging(settings.fastramqpi.log_level, settings.production)

    # ldap_ou_for_new_users needs to be in the search base. Otherwise we cannot
    # find newly created users...
    check_ou_in_list_of_ous(
        settings.ldap_ou_for_new_users,
        settings.ldap_ous_to_search_in,
    )

    # We also need to check for permission to write to this OU
    check_ou_in_list_of_ous(
        settings.ldap_ou_for_new_users,
        settings.ldap_ous_to_write_to,
    )

    logger.info("Setting up FastRAMQPI")
    fastramqpi = FastRAMQPI(
        application_name="ldap_ie",
        settings=settings.fastramqpi,
        graphql_version=22,
        graphql_client_cls=GraphQLClient,
    )
    fastramqpi.add_context(settings=settings)

    logger.info("AMQP router setup")
    amqpsystem = fastramqpi.get_amqpsystem()
    amqpsystem.dependencies = [
        Depends(rate_limit(delay_on_error)),
        Depends(depends.logger_bound_message_id),
        Depends(depends.request_id),
    ]
    if settings.listen_to_changes_in_mo:
        amqpsystem.router.registry.update(amqp_router.registry)

    # We delay AMQPSystem start, to detect it from client startup
    # TODO: This separation should probably be in FastRAMQPI
    priority_set = fastramqpi._context["lifespan_managers"][1000]
    priority_set.remove(amqpsystem)
    fastramqpi.add_lifespan_manager(amqpsystem, 2000)

    logger.info("Configuring LDAP connection")
    ldap_connection = configure_ldap_connection(settings)
    fastramqpi.add_context(ldap_connection=ldap_connection)
    fastramqpi.add_healthcheck(name="LDAPConnection", healthcheck=ldap_healthcheck)
    fastramqpi.add_lifespan_manager(
        open_ldap_connection(ldap_connection),  # type: ignore
        1100,
    )

    logger.info("Loading mapping file")
    mapping = settings.conversion_mapping.dict(exclude_unset=True, by_alias=True)
    fastramqpi.add_context(mapping=mapping)

    logger.info("Initializing dataloader")
    dataloader = DataLoader(fastramqpi.get_context())
    fastramqpi.add_context(dataloader=dataloader)

    userNameGeneratorClass_string = mapping["username_generator"]["objectClass"]
    logger.info("Initializing username generator")
    username_generator_class = get_username_generator_class(
        userNameGeneratorClass_string
    )
    username_generator = username_generator_class(fastramqpi.get_context())
    fastramqpi.add_context(username_generator=username_generator)

    fastramqpi.add_lifespan_manager(initialize_init_engine(fastramqpi), 1200)
    fastramqpi.add_lifespan_manager(initialize_converters(fastramqpi), 1250)

    # NOTE: info_dict_refresher depends on converters
    fastramqpi.add_lifespan_manager(initialize_info_dict_refresher(fastramqpi), 1275)

    fastramqpi.add_lifespan_manager(initialize_checks(fastramqpi), 1300)
    fastramqpi.add_lifespan_manager(initialize_sync_tool(fastramqpi), 1350)

    if settings.listen_to_changes_in_ldap:
        fastramqpi.add_lifespan_manager(initialize_ldap_listener(fastramqpi), 1400)
        configure_ldap_amqpsystem(fastramqpi, settings.ldap_amqp, 2000)

    return fastramqpi


def create_app(fastramqpi: FastRAMQPI | None = None, **kwargs: Any) -> FastAPI:
    """FastAPI application factory.

    Returns:
        FastAPI application.
    """
    if fastramqpi is None:
        fastramqpi = create_fastramqpi(**kwargs)
    assert fastramqpi is not None

    app = fastramqpi.get_app()
    app.include_router(fastapi_router)

    user_context = fastramqpi._context["user_context"]
    app.include_router(construct_router(user_context))

    return app
