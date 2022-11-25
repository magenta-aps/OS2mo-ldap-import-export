# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
"""Event handling."""
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from typing import Tuple

import structlog
from fastapi import APIRouter
from fastapi import FastAPI
from fastapi import Request
from fastapi import Response
from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastramqpi.context import Context
from fastramqpi.main import FastRAMQPI
from ldap3 import Connection
from pydantic import ValidationError
from raclients.graph.client import PersistentGraphQLClient
from raclients.modelclient.mo import ModelClient
from ramodels.mo.details.address import Address
from ramodels.mo.employee import Employee
from ramqp.mo import MORouter
from ramqp.mo.models import ObjectType
from ramqp.mo.models import PayloadType
from ramqp.mo.models import RequestType
from ramqp.utils import RejectMessage

from .config import Settings
from .converters import LdapConverter
from .converters import read_mapping_json
from .dataloaders import configure_dataloaders
from .ldap import configure_ldap_connection
from .ldap import ldap_healthcheck
from .ldap_classes import LdapObject

# from .converters import check_mapping

logger = structlog.get_logger()
fastapi_router = APIRouter()
amqp_router = MORouter()

"""
Employee.schema()
help(MORouter)
help(ServiceType)
help(ObjectType)
help(RequestType)
"""


@amqp_router.register("employee.*.*")
async def listen_to_changes_in_employees(
    context: Context, payload: PayloadType, **kwargs: Any
) -> None:

    user_context = context["user_context"]
    converter = user_context["converter"]
    logger.info(f"Payload: {payload}")

    # TODO: Add support for deleting users / fields from LDAP
    if kwargs["mo_routing_key"].request_type == RequestType.TERMINATE:
        raise RejectMessage("Not supported")

    mo_address_loader = user_context["dataloaders"].mo_address_loader
    mo_employee_loader = user_context["dataloaders"].mo_employee_loader

    # Get MO employee
    changed_employee: Employee = await mo_employee_loader.load(payload.uuid)
    logger.info(f"Found Employee in MO: {changed_employee}")

    mo_object_dict = {"mo_employee": changed_employee}

    if kwargs["mo_routing_key"].object_type == ObjectType.EMPLOYEE:
        logger.info("[MO] Change registered in the employee model")

        # Convert to LDAP
        ldap_employee = converter.to_ldap(mo_object_dict, "Employee")

        # Upload to LDAP
        await user_context["dataloaders"].ldap_object_uploader.load(
            (ldap_employee, "Employee")
        )

    elif kwargs["mo_routing_key"].object_type == ObjectType.ADDRESS:
        logger.info("[MO] Change registered in the address model")

        # Get MO address
        changed_address, meta_info = await mo_address_loader.load(payload.object_uuid)
        address_type = meta_info["address_type_name"]

        logger.info(f"Obtained address type = {address_type}")

        # Convert to LDAP
        mo_object_dict["mo_address"] = changed_address
        ldap_address = converter.to_ldap(mo_object_dict, address_type)

        # Upload to LDAP
        await user_context["dataloaders"].ldap_object_uploader.load(
            (ldap_address, address_type)
        )


@asynccontextmanager
async def open_ldap_connection(ldap_connection: Connection) -> AsyncIterator[None]:
    """Open the LDAP connection during FastRAMQPI lifespan.

    Yields:
        None
    """
    with ldap_connection:
        yield


@asynccontextmanager
async def seed_dataloaders(fastramqpi: FastRAMQPI) -> AsyncIterator[None]:
    """Seed dataloaders during FastRAMQPI lifespan.

    Yields:
        None
    """
    logger.info("Seeding dataloaders")
    context = fastramqpi.get_context()
    dataloaders = configure_dataloaders(context)
    fastramqpi.add_context(dataloaders=dataloaders)
    yield


def construct_gql_client(settings: Settings):
    return PersistentGraphQLClient(
        url=settings.mo_url + "/graphql/v2",
        client_id=settings.client_id,
        client_secret=settings.client_secret.get_secret_value(),
        auth_server=settings.auth_server,
        auth_realm=settings.auth_realm,
        execute_timeout=settings.graphql_timeout,
        httpx_client_kwargs={"timeout": settings.graphql_timeout},
    )


def construct_model_client(settings: Settings):
    return ModelClient(
        base_url=settings.mo_url,
        client_id=settings.client_id,
        client_secret=settings.client_secret.get_secret_value(),
        auth_server=settings.auth_server,
        auth_realm=settings.auth_realm,
    )


def construct_clients(
    settings: Settings,
) -> Tuple[PersistentGraphQLClient, ModelClient]:
    """Construct clients froms settings.

    Args:
        settings: Integration settings module.

    Returns:
        Tuple with PersistentGraphQLClient and ModelClient.
    """
    gql_client = construct_gql_client(settings)
    model_client = construct_model_client(settings)
    return gql_client, model_client


def create_fastramqpi(**kwargs: Any) -> FastRAMQPI:
    """FastRAMQPI factory.

    Returns:
        FastRAMQPI system.
    """
    logger.info("Retrieving settings")
    settings = Settings(**kwargs)

    logger.info("Setting up FastRAMQPI")
    fastramqpi = FastRAMQPI(application_name="ad2mosync", settings=settings.fastramqpi)
    fastramqpi.add_context(settings=settings)

    logger.info("AMQP router setup")
    amqpsystem = fastramqpi.get_amqpsystem()
    amqpsystem.router.registry.update(amqp_router.registry)

    logger.info("Setting up clients")
    gql_client, model_client = construct_clients(settings)
    fastramqpi.add_context(model_client=model_client)
    fastramqpi.add_context(gql_client=gql_client)

    logger.info("Configuring LDAP connection")
    ldap_connection = configure_ldap_connection(settings)
    fastramqpi.add_context(ldap_connection=ldap_connection)
    fastramqpi.add_healthcheck(name="LDAPConnection", healthcheck=ldap_healthcheck)
    fastramqpi.add_lifespan_manager(open_ldap_connection(ldap_connection), 1500)
    fastramqpi.add_lifespan_manager(seed_dataloaders(fastramqpi), 2000)

    logger.info("Configuring Dataloaders")
    context = fastramqpi.get_context()
    dataloaders = configure_dataloaders(context)
    fastramqpi.add_context(dataloaders=dataloaders)

    logger.info("Loading mapping file")
    mappings_folder = os.path.join(os.path.dirname(__file__), "mappings")
    mappings_file = os.path.join(mappings_folder, "default.json")
    fastramqpi.add_context(mapping=read_mapping_json(mappings_file))

    logger.info("Initializing converters")
    converter = LdapConverter(context)
    fastramqpi.add_context(cpr_field=converter.cpr_field)
    fastramqpi.add_context(converter=converter)
    fastramqpi.add_lifespan_manager(converter.check_mapping(), 2500)

    return fastramqpi


def encode_result(result):
    # This removes all bytes objects from the result. for example images
    json_compatible_result = jsonable_encoder(
        result, custom_encoder={bytes: lambda v: None}
    )
    return json_compatible_result


def create_app(**kwargs: Any) -> FastAPI:
    """FastAPI application factory.

    Returns:
        FastAPI application.
    """
    fastramqpi = create_fastramqpi(**kwargs)

    app = fastramqpi.get_app()
    app.include_router(fastapi_router)

    user_context = fastramqpi._context["user_context"]
    dataloaders = user_context["dataloaders"]
    converter = user_context["converter"]

    # Get all objects from LDAP - Converted to MO
    @app.get("/LDAP/{json_key}/converted", status_code=202)
    async def convert_all_org_persons_from_ldap(json_key: str) -> Any:
        """Request all organizational persons, converted to MO"""
        logger.info("Manually triggered LDAP request of all organizational persons")

        result = await dataloaders.ldap_objects_loader.load(json_key)
        converted_results = []
        for r in result:
            try:
                converted_results.append(converter.from_ldap(r, json_key))
            except ValidationError as e:
                logger.error(f"Cannot convert {r} to MO {json_key}: {e}")
        return converted_results

    # Get a specific cpr-indexed object from LDAP
    @app.get("/LDAP/{json_key}/{cpr}", status_code=202)
    async def load_object_from_LDAP(json_key: str, cpr: str, request: Request) -> Any:
        """Request single ldap object"""
        logger.info(f"Manually triggered LDAP request of {cpr}")

        result = await dataloaders.ldap_object_loader.load((cpr, json_key))
        return encode_result(result)

    # Get a specific cpr-indexed object from LDAP - Converted to MO
    @app.get("/LDAP/{json_key}/{cpr}/converted", status_code=202)
    async def convert_object_from_LDAP(
        json_key: str, cpr: str, request: Request, response: Response
    ) -> Any:
        """Request single ldap object and convert it to a MO object"""
        logger.info(f"Manually triggered LDAP request of {cpr}")

        result = await dataloaders.ldap_object_loader.load((cpr, json_key))
        try:
            return converter.from_ldap(result, json_key)
        except ValidationError as e:
            logger.error(f"Cannot convert {result} to MO {json_key}: {e}")
            response.status_code = (
                status.HTTP_404_NOT_FOUND
            )  # TODO: return other status?
            return None

    # Get all objects from LDAP
    @app.get("/LDAP/{json_key}", status_code=202)
    async def load_all_objects_from_LDAP(json_key: str) -> Any:
        """Request all ldap objects"""
        logger.info(f"Manually triggered LDAP request of all {json_key} objects")

        result = await dataloaders.ldap_objects_loader.load(json_key)

        return encode_result(result)

    # Modify a person in LDAP
    @app.post("/LDAP/{json_key}")
    async def post_object_to_LDAP(json_key: str, ldap_object: LdapObject) -> Any:
        logger.info(f"Posting {ldap_object} to LDAP")

        await dataloaders.ldap_object_uploader.load((ldap_object, json_key))

    # Post a person to MO
    @app.post("/MO/Employee")
    async def post_employee_to_MO(employee: Employee) -> Any:
        logger.info(f"Posting employee={employee} to MO")

        await dataloaders.mo_employee_uploader.load(employee)

    # Post an address to MO
    @app.post("/MO/address")
    async def post_address_to_MO(address: Address) -> Any:
        logger.info(f"Posting address={address} to MO")

        await dataloaders.mo_address_uploader.load(address)

    # Get a speficic address from MO
    @app.get("/MO/address/{uuid}", status_code=202)
    async def load_address_from_MO(uuid: str, request: Request) -> Any:
        """Request single address"""
        logger.info(f"Manually triggered MO address request of {uuid}")

        result = await dataloaders.mo_address_loader.load(uuid)
        return result

    # Get a speficic person from MO
    @app.get("/MO/Employee/{uuid}", status_code=202)
    async def load_employee_from_MO(uuid: str, request: Request) -> Any:
        """Request single employee"""
        logger.info(f"Manually triggered MO request of {uuid}")

        result = await dataloaders.mo_employee_loader.load(uuid)
        return result

    # Get LDAP overview
    @app.get("/LDAP_overview", status_code=202)
    async def load_overview_from_LDAP() -> Any:
        """Request an overview of the LDAP structure"""
        logger.info("Manually triggered LDAP request of overview")

        result = await dataloaders.ldap_overview_loader.load(1)
        return result

    # Get populated LDAP overview
    @app.get("/LDAP_overview/populated", status_code=202)
    async def load_populated_overview_from_LDAP() -> Any:
        """Request a populated overview of the LDAP structure"""
        logger.info("Manually triggered LDAP request of populated overview")

        result = await dataloaders.ldap_populated_overview_loader.load(1)
        return result

    # Get MO address types
    @app.get("/MO/address_types", status_code=202)
    async def load_address_types_from_MO() -> Any:
        """Request all address types from MO"""
        result = await dataloaders.mo_address_type_loader.load(1)
        return result

    return app
