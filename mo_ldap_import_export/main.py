# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
"""Event handling."""
import datetime
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any
from typing import Callable
from typing import Literal
from typing import Tuple
from uuid import UUID
from uuid import uuid4

import structlog
from fastapi import APIRouter
from fastapi import Depends
from fastapi import FastAPI
from fastapi import Request
from fastapi import Response
from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_login import LoginManager
from fastapi_login.exceptions import InvalidCredentialsException
from fastramqpi.context import Context
from fastramqpi.main import FastRAMQPI
from gql.transport.exceptions import TransportQueryError
from ldap3 import Connection
from pydantic import ValidationError
from raclients.graph.client import PersistentGraphQLClient
from raclients.modelclient.mo import ModelClient
from ramqp.mo import MORouter
from ramqp.mo.models import ObjectType
from ramqp.mo.models import PayloadType
from ramqp.mo.models import RequestType
from ramqp.mo.models import ServiceType
from ramqp.utils import RejectMessage
from tqdm import tqdm

from . import usernames
from .config import Settings
from .converters import LdapConverter
from .converters import read_mapping_json
from .dataloaders import DataLoader
from .exceptions import IncorrectMapping
from .exceptions import MultipleObjectsReturnedException
from .exceptions import NotSupportedException
from .ldap import cleanup
from .ldap import configure_ldap_connection
from .ldap import get_attribute_types
from .ldap import ldap_healthcheck
from .ldap_classes import LdapObject

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

# UUIDs in this list will be ignored by listen_to_changes ONCE
uuids_to_ignore: dict[UUID, list[datetime.datetime]] = {}


def reject_on_failure(func):
    """
    Decorator to turn message into dead letter in case of exceptions.
    """

    async def modified_func(*args, **kwargs):
        try:
            await func(*args, **kwargs)
        except (NotSupportedException, IncorrectMapping, TransportQueryError) as e:
            logger.exception(e)
            raise RejectMessage()

    modified_func.__wrapped__ = func  # type: ignore
    return modified_func


async def listen_to_changes_in_employees(
    context: Context, payload: PayloadType, **kwargs: Any
) -> None:

    routing_key = kwargs["mo_routing_key"]
    logger.info("[MO] Registered change in the employee model")

    user_context = context["user_context"]
    dataloader = user_context["dataloader"]
    converter = user_context["converter"]

    # Get MO employee
    changed_employee = await dataloader.load_mo_employee(payload.uuid)
    logger.info(f"Found Employee in MO: {changed_employee}")

    mo_object_dict: dict[str, Any] = {"mo_employee": changed_employee}

    if routing_key.object_type == ObjectType.EMPLOYEE:
        logger.info("[MO] Change registered in the employee object type")

        # Convert to LDAP
        ldap_employee = converter.to_ldap(mo_object_dict, "Employee")

        # Upload to LDAP - overwrite because all employee fields are unique.
        # One person cannot have multiple names.
        await dataloader.upload_ldap_object(ldap_employee, "Employee", overwrite=True)

    elif routing_key.object_type == ObjectType.ADDRESS:
        logger.info("[MO] Change registered in the address object type")

        # Get MO address
        changed_address, meta_info = await dataloader.load_mo_address(
            payload.object_uuid
        )
        address_type = json_key = meta_info["address_type_user_key"]

        logger.info(f"Obtained address type = {address_type}")
        mo_object_dict["mo_employee_address"] = changed_address

        # Convert & Upload to LDAP
        await dataloader.upload_ldap_object(
            converter.to_ldap(mo_object_dict, json_key), json_key
        )

        addresses_in_mo = await dataloader.load_mo_employee_addresses(
            changed_employee.uuid, changed_address.address_type.uuid
        )

        cleanup(
            json_key,
            "value",
            "mo_employee_address",
            [a[0] for a in addresses_in_mo],
            user_context,
            changed_employee,
        )

    elif routing_key.object_type == ObjectType.IT:
        logger.info("[MO] Change registered in the IT object type")

        # Get MO IT-user
        changed_it_user = await dataloader.load_mo_it_user(payload.object_uuid)
        it_system_type_uuid = changed_it_user.itsystem.uuid
        it_system_name = json_key = converter.get_it_system_name(it_system_type_uuid)

        logger.info(f"Obtained IT system name = {it_system_name}")
        mo_object_dict["mo_employee_it_user"] = changed_it_user

        # Convert & Upload to LDAP
        await dataloader.upload_ldap_object(
            converter.to_ldap(mo_object_dict, json_key), json_key
        )

        # Load IT users belonging to this employee
        it_users_in_mo = await dataloader.load_mo_employee_it_users(
            changed_employee.uuid, it_system_type_uuid
        )

        cleanup(
            json_key,
            "user_key",
            "mo_employee_it_user",
            it_users_in_mo,
            user_context,
            changed_employee,
        )

    elif routing_key.object_type == ObjectType.ENGAGEMENT:
        logger.info("[MO] Change registered in the Engagement object type")

        # Get MO Engagement
        changed_engagement = await dataloader.load_mo_engagement(payload.object_uuid)

        json_key = "Engagement"
        mo_object_dict["mo_employee_engagement"] = changed_engagement

        # Convert & Upload to LDAP
        await dataloader.upload_ldap_object(
            converter.to_ldap(mo_object_dict, json_key), json_key
        )

        engagements_in_mo = await dataloader.load_mo_employee_engagements(
            changed_employee.uuid
        )

        cleanup(
            json_key,
            "user_key",
            "mo_employee_engagement",
            engagements_in_mo,
            user_context,
            changed_employee,
        )


async def listen_to_changes_in_org_units(
    context: Context, payload: PayloadType, **kwargs: Any
) -> None:

    user_context = context["user_context"]
    dataloader = user_context["dataloader"]
    converter = user_context["converter"]

    # When an org-unit is changed we need to update the org unit info. So we
    # know the new name of the org unit in case it was changed
    logger.info("Updating org unit info")
    converter.org_unit_info = dataloader.load_mo_org_units()
    converter.check_org_unit_info_dict()


@amqp_router.register("*.*.*")
@reject_on_failure
async def listen_to_changes(
    context: Context, payload: PayloadType, **kwargs: Any
) -> None:
    global uuids_to_ignore
    routing_key = kwargs["mo_routing_key"]

    # Remove all timestamps which have been in this dict for more than 60 seconds.
    now = datetime.datetime.now()
    for uuid, timestamps in uuids_to_ignore.items():
        for timestamp in timestamps:
            age_in_seconds = (now - timestamp).total_seconds()
            if age_in_seconds > 60:
                logger.info(
                    (
                        f"Removing timestamp belonging to {uuid} from uuids_to_ignore. "
                        f"It is {age_in_seconds} seconds old"
                    )
                )
                timestamps.remove(timestamp)

    # If the object was uploaded by us, it does not need to be synchronized.
    if (
        payload.object_uuid in uuids_to_ignore
        and uuids_to_ignore[payload.object_uuid]
        and routing_key.service_type == ServiceType.EMPLOYEE
    ):
        logger.info(f"[listen_to_changes] Ignoring {routing_key}-{payload.object_uuid}")

        # Remove timestamp so it does not get ignored twice.
        oldest_timestamp = min(uuids_to_ignore[payload.object_uuid])
        uuids_to_ignore[payload.object_uuid].remove(oldest_timestamp)
        return None

    # If we are not supposed to listen: reject and turn the message into a dead letter.
    elif not Settings().listen_to_changes_in_mo:
        raise RejectMessage()

    logger.info(f"[MO] Routing key: {routing_key}")
    logger.info(f"[MO] Payload: {payload}")

    # TODO: Add support for deleting users / fields from LDAP
    if routing_key.request_type == RequestType.TERMINATE:
        # Note: Deleting an object is not straightforward, because MO specifies a future
        # date, on which the object is to be deleted. We would need a job which runs
        # daily and checks for users/addresses/etc... that need to be deleted
        raise NotSupportedException("Terminations are not supported")

    if routing_key.service_type == ServiceType.EMPLOYEE:
        await listen_to_changes_in_employees(context, payload, **kwargs)
    elif routing_key.service_type == ServiceType.ORG_UNIT:
        await listen_to_changes_in_org_units(context, payload, **kwargs)


@asynccontextmanager
async def open_ldap_connection(ldap_connection: Connection) -> AsyncIterator[None]:
    """Open the LDAP connection during FastRAMQPI lifespan.

    Yields:
        None
    """
    with ldap_connection:
        yield


def construct_gql_client(settings: Settings, sync=False):
    return PersistentGraphQLClient(
        url=settings.mo_url + "/graphql/v2",
        client_id=settings.client_id,
        client_secret=settings.client_secret.get_secret_value(),
        auth_server=settings.auth_server,
        auth_realm=settings.auth_realm,
        execute_timeout=settings.graphql_timeout,
        httpx_client_kwargs={"timeout": settings.graphql_timeout},
        sync=sync,
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
) -> Tuple[PersistentGraphQLClient, PersistentGraphQLClient, ModelClient]:
    """Construct clients froms settings.

    Args:
        settings: Integration settings module.

    Returns:
        Tuple with PersistentGraphQLClient and ModelClient.
    """
    gql_client = construct_gql_client(settings)
    gql_client_sync = construct_gql_client(settings, sync=True)
    model_client = construct_model_client(settings)
    return gql_client, gql_client_sync, model_client


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
    gql_client, gql_client_sync, model_client = construct_clients(settings)
    fastramqpi.add_context(model_client=model_client)
    fastramqpi.add_context(gql_client=gql_client)
    fastramqpi.add_context(gql_client_sync=gql_client_sync)

    logger.info("Configuring LDAP connection")
    ldap_connection = configure_ldap_connection(settings)
    fastramqpi.add_context(ldap_connection=ldap_connection)
    fastramqpi.add_healthcheck(name="LDAPConnection", healthcheck=ldap_healthcheck)
    fastramqpi.add_lifespan_manager(open_ldap_connection(ldap_connection), 1500)

    logger.info("Loading mapping file")
    mappings_file = os.environ.get("CONVERSION_MAP")
    if not mappings_file:
        mappings_file = "magenta_demo.json"
        logger.warning(f"CONVERSION_MAP is not set, falling back to {mappings_file}")
    mappings_file = os.path.normpath(
        mappings_file
        if mappings_file.startswith("/")
        else os.path.join(os.path.dirname(__file__), "mappings", mappings_file)
    )
    if not os.path.isfile(mappings_file):
        raise FileNotFoundError(
            f"Configured mapping file {mappings_file} does not exist "
            f"(this is set by the CONVERSION_MAP environment variable)"
        )
    mapping = read_mapping_json(mappings_file)
    fastramqpi.add_context(mapping=mapping)
    logger.info(f"Loaded mapping file {mappings_file}")

    logger.info("Initializing dataloader")
    dataloader = DataLoader(fastramqpi.get_context())
    fastramqpi.add_context(dataloader=dataloader)

    userNameGeneratorClass_string = mapping["username_generator"]["objectClass"]
    logger.info(f"Importing {userNameGeneratorClass_string}")
    UserNameGenerator = getattr(usernames, userNameGeneratorClass_string)

    logger.info("Initializing username generator")
    username_generator = UserNameGenerator(fastramqpi.get_context())
    fastramqpi.add_context(username_generator=username_generator)

    if not hasattr(username_generator, "generate_dn"):
        raise AttributeError("Username generator needs to have a generate_dn function")

    logger.info("Initializing converters")
    converter = LdapConverter(fastramqpi.get_context())
    fastramqpi.add_context(cpr_field=converter.cpr_field)
    fastramqpi.add_context(converter=converter)

    return fastramqpi


def encode_result(result):
    # This removes all bytes objects from the result. for example images
    json_compatible_result = jsonable_encoder(
        result, custom_encoder={bytes: lambda v: None}
    )
    return json_compatible_result


async def format_converted_objects(
    converted_objects, json_key, employee_uuid, user_context
):
    """
    for Address and Engagement objects:
        Loops through the objects, and sets the uuid if an existing matching object is
        found
    for ITUser objects:
        Loops through the objects and removes it if an existing matchin object is found
    for all other objects:
        returns the input list of converted_objects
    """

    converter = user_context["converter"]
    dataloader = user_context["dataloader"]
    mo_object_class = converter.find_mo_object_class(json_key).split(".")[-1]

    # Load addresses already in MO
    if mo_object_class == "Address":
        addresses_in_mo = await dataloader.load_mo_employee_addresses(
            employee_uuid, converted_objects[0].address_type.uuid
        )
        value_key = "value"
        objects_in_mo = [o[0] for o in addresses_in_mo]
    # Load engagements already in MO
    elif mo_object_class == "Engagement":
        objects_in_mo = await dataloader.load_mo_employee_engagements(employee_uuid)
        value_key = "user_key"

    elif mo_object_class == "ITUser":
        # If an ITUser already exists, MO throws an error - it cannot be updated if the
        # key is identical to an existing key.
        it_users_in_mo = await dataloader.load_mo_employee_it_users(
            employee_uuid, converted_objects[0].itsystem.uuid
        )
        user_keys_in_mo = [a.user_key for a in it_users_in_mo]

        return [
            converted_object
            for converted_object in converted_objects
            if converted_object.user_key not in user_keys_in_mo
        ]

    else:
        return converted_objects

    objects_in_mo_dict = {a.uuid: a for a in objects_in_mo}
    mo_attributes = converter.get_mo_attributes(json_key)

    # Set uuid if a matching one is found. so an object gets updated
    # instead of duplicated
    converted_objects_uuid_checked = []
    for converted_object in converted_objects:
        values_in_mo = [getattr(a, value_key) for a in objects_in_mo_dict.values()]
        converted_object_value = getattr(converted_object, value_key)

        if values_in_mo.count(converted_object_value) == 1:
            logger.info(
                (
                    f"Found matching MO '{json_key}' with "
                    f"value='{getattr(converted_object,value_key)}'"
                )
            )

            for uuid, mo_object in objects_in_mo_dict.items():
                value = getattr(mo_object, value_key)
                if value == converted_object_value:
                    matching_object_uuid = uuid
                    break

            matching_object = objects_in_mo_dict[matching_object_uuid]
            converted_mo_object_dict = converted_object.dict()

            mo_object_dict_to_upload = matching_object.dict()
            for key in mo_attributes:
                if (
                    key not in ["validity", "uuid", "objectClass"]
                    and key in converted_mo_object_dict.keys()
                ):
                    logger.info(f"Setting {key} = {converted_mo_object_dict[key]}")
                    mo_object_dict_to_upload[key] = converted_mo_object_dict[key]

            mo_class = converter.import_mo_object_class(json_key)
            converted_objects_uuid_checked.append(mo_class(**mo_object_dict_to_upload))
        elif values_in_mo.count(converted_object_value) == 0:
            converted_objects_uuid_checked.append(converted_object)
        else:
            logger.warning(
                f"Could not determine which '{json_key}' MO object "
                f"{value_key}='{converted_object_value}' belongs to. Skipping"
            )

    return converted_objects_uuid_checked


def create_app(**kwargs: Any) -> FastAPI:
    """FastAPI application factory.

    Returns:
        FastAPI application.
    """
    fastramqpi = create_fastramqpi(**kwargs)
    settings = Settings(**kwargs)

    app = fastramqpi.get_app()
    app.include_router(fastapi_router)

    login_manager = LoginManager(
        settings.authentication_secret.get_secret_value(),
        "/login",
        default_expiry=timedelta(hours=settings.token_expiry_time),
    )

    user_database = {
        "admin": {
            "password": settings.admin_password.get_secret_value(),
        }
    }
    user_loader: Callable = login_manager.user_loader

    @user_loader()
    def query_user(user_id: str):
        return user_database.get(user_id)

    context = fastramqpi._context
    user_context = context["user_context"]
    converter = user_context["converter"]
    dataloader = user_context["dataloader"]
    ldap_connection = user_context["ldap_connection"]

    attribute_types = get_attribute_types(ldap_connection)
    accepted_attributes = tuple(sorted(attribute_types.keys()))

    ldap_classes = tuple(sorted(converter.overview.keys()))
    default_ldap_class = converter.raw_mapping["mo_to_ldap"]["Employee"]["objectClass"]

    accepted_json_keys = tuple(converter.get_accepted_json_keys())
    detected_json_keys = converter.get_ldap_to_mo_json_keys()

    @app.post("/login")
    def login(data: OAuth2PasswordRequestForm = Depends()):
        user_id = data.username
        password = data.password

        user = query_user(user_id)
        if not user or password != user["password"]:
            raise InvalidCredentialsException

        access_token = login_manager.create_access_token(data={"sub": user_id})
        return {"access_token": access_token}

    # Load all users from LDAP, and import them into MO
    @app.get("/Import/all", status_code=202, tags=["Import"])
    async def import_all_objects_from_LDAP(
        test_on_first_20_entries: bool = False, user=Depends(login_manager)
    ) -> Any:
        all_ldap_objects = await dataloader.load_ldap_objects("Employee")
        all_cpr_numbers = [o.dict()[converter.cpr_field] for o in all_ldap_objects]
        all_cpr_numbers = sorted(list(set([a for a in all_cpr_numbers if a])))

        if test_on_first_20_entries:
            # Only upload the first 20 entries
            logger.info("Slicing the first 20 entries")
            all_cpr_numbers = all_cpr_numbers[:20]

        number_of_entries = len(all_cpr_numbers)
        logger.info(f"Found {number_of_entries} cpr-indexed entries in AD")

        with tqdm(total=number_of_entries, unit="ldap object") as progress_bar:
            progress_bar.set_description("LDAP import progress")

            # Note: This can be done in a more parallel way using asyncio.gather() but:
            # - it was experienced that fastapi throws broken pipe errors
            # - MO was observed to not handle that well either.
            # - We don't need the additional speed. This is meant as a one-time import
            for cpr in all_cpr_numbers:
                await import_single_user_from_LDAP(cpr)
                progress_bar.update()

    # Load a single user from LDAP, and import him/her/hir into MO
    @app.get("/Import/{cpr}", status_code=202, tags=["Import"])
    async def import_single_user_from_LDAP(
        cpr: str, user=Depends(login_manager)
    ) -> Any:
        global uuids_to_ignore
        # Get the employee's uuid (if he exists)
        # Note: We could optimize this by loading all relevant employees once. But:
        # - What if an employee is created by someone else while this code is running?
        # - We don't need the additional speed. This is meant as a one-time import
        # - We won't gain much; This is an asynchronous request. The code moves on while
        #   we are waiting for MO's response
        employee_uuid = await dataloader.find_mo_employee_uuid(cpr)
        if not employee_uuid:
            employee_uuid = uuid4()

        # First import the Employee
        # Then import other objects (which link to the employee)
        json_keys = ["Employee"] + [k for k in detected_json_keys if k != "Employee"]

        for json_key in json_keys:
            logger.info(f"Loading {json_key} object")
            try:
                loaded_object = dataloader.load_ldap_cpr_object(cpr, json_key)
            except MultipleObjectsReturnedException as e:
                logger.warning(f"Could not upload {json_key} object: {e}")
                break

            logger.info(f"Loaded {loaded_object.dn}")

            converted_objects = converter.from_ldap(
                loaded_object, json_key, employee_uuid=employee_uuid
            )

            if len(converted_objects) == 0:
                logger.info("No converted objects")
                continue

            converted_objects = await format_converted_objects(
                converted_objects, json_key, employee_uuid, user_context
            )

            if len(converted_objects) > 0:
                logger.info(f"Importing {converted_objects}")

                for mo_object in converted_objects:
                    if mo_object.uuid in uuids_to_ignore:
                        uuids_to_ignore[mo_object.uuid].append(datetime.datetime.now())
                    else:
                        uuids_to_ignore[mo_object.uuid] = [datetime.datetime.now()]
                await dataloader.upload_mo_objects(converted_objects)

    # Get all objects from LDAP - Converted to MO
    @app.get("/LDAP/{json_key}/converted", status_code=202, tags=["LDAP"])
    async def convert_all_objects_from_ldap(
        json_key: Literal[accepted_json_keys],  # type: ignore
        user=Depends(login_manager),
    ) -> Any:
        result = await dataloader.load_ldap_objects(json_key)
        converted_results = []
        for r in result:
            try:
                converted_results.extend(
                    converter.from_ldap(r, json_key, employee_uuid=uuid4())
                )
            except ValidationError as e:
                logger.error(f"Cannot convert {r} to MO {json_key}: {e}")
        return converted_results

    # Get a specific cpr-indexed object from LDAP
    @app.get("/LDAP/{json_key}/{cpr}", status_code=202, tags=["LDAP"])
    async def load_object_from_LDAP(
        json_key: Literal[accepted_json_keys],  # type: ignore
        cpr: str,
        user=Depends(login_manager),
    ) -> Any:
        result = dataloader.load_ldap_cpr_object(cpr, json_key)
        return encode_result(result)

    # Get a specific cpr-indexed object from LDAP - Converted to MO
    @app.get("/LDAP/{json_key}/{cpr}/converted", status_code=202, tags=["LDAP"])
    async def convert_object_from_LDAP(
        json_key: Literal[accepted_json_keys],  # type: ignore
        cpr: str,
        response: Response,
        user=Depends(login_manager),
    ) -> Any:
        result = dataloader.load_ldap_cpr_object(cpr, json_key)
        try:
            return converter.from_ldap(result, json_key, employee_uuid=uuid4())
        except ValidationError as e:
            logger.error(f"Cannot convert {result} to MO {json_key}: {e}")
            response.status_code = (
                status.HTTP_404_NOT_FOUND
            )  # TODO: return other status?
            return None

    # Get all objects from LDAP
    @app.get("/LDAP/{json_key}", status_code=202, tags=["LDAP"])
    async def load_all_objects_from_LDAP(
        json_key: Literal[accepted_json_keys],  # type: ignore
        user=Depends(login_manager),
    ) -> Any:
        result = await dataloader.load_ldap_objects(json_key)
        return encode_result(result)

    # Modify a person in LDAP
    @app.post("/LDAP/{json_key}", tags=["LDAP"])
    async def post_object_to_LDAP(
        json_key: Literal[accepted_json_keys],  # type: ignore
        ldap_object: LdapObject,
        user=Depends(login_manager),
    ) -> Any:
        await dataloader.upload_ldap_object(ldap_object, json_key)

    # Post an object to MO
    @app.post("/MO/{json_key}", tags=["MO"])
    async def post_object_to_MO(
        json_key: Literal[accepted_json_keys],  # type: ignore
        mo_object_json: dict,
        user=Depends(login_manager),
    ) -> None:
        mo_object = converter.import_mo_object_class(json_key)
        logger.info(f"Posting {mo_object} = {mo_object_json} to MO")
        await dataloader.upload_mo_objects([mo_object(**mo_object_json)])

    # Get a speficic address from MO
    @app.get("/MO/Address/{uuid}", status_code=202, tags=["MO"])
    async def load_address_from_MO(
        uuid: UUID, request: Request, user=Depends(login_manager)
    ) -> Any:
        result = await dataloader.load_mo_address(uuid)
        return result

    # Get a speficic person from MO
    @app.get("/MO/Employee/{uuid}", status_code=202, tags=["MO"])
    async def load_employee_from_MO(
        uuid: UUID, request: Request, user=Depends(login_manager)
    ) -> Any:
        result = await dataloader.load_mo_employee(uuid)
        return result

    # Get LDAP overview
    @app.get("/LDAP_overview", status_code=202, tags=["LDAP"])
    async def load_overview_from_LDAP(
        user=Depends(login_manager),
        ldap_class: Literal[ldap_classes] = default_ldap_class,  # type: ignore
    ) -> Any:
        ldap_overview = dataloader.load_ldap_overview()
        return ldap_overview[ldap_class]

    # Get populated LDAP overview
    @app.get("/LDAP_overview/populated", status_code=202, tags=["LDAP"])
    async def load_populated_overview_from_LDAP(
        user=Depends(login_manager),
        ldap_class: Literal[ldap_classes] = default_ldap_class,  # type: ignore
    ) -> Any:
        ldap_overview = dataloader.load_ldap_populated_overview(
            ldap_classes=[ldap_class]
        )
        return encode_result(ldap_overview.get(ldap_class))

    # Get LDAP attribute details
    @app.get("/LDAP_overview/attribute_details", status_code=202, tags=["LDAP"])
    async def load_attribute_details_from_LDAP(
        attribute: Literal[accepted_attributes],  # type: ignore
        user=Depends(login_manager),
    ) -> Any:
        return attribute_types[attribute]

    # Get MO address types
    @app.get("/MO/Address_types", status_code=202, tags=["MO"])
    async def load_address_types_from_MO(user=Depends(login_manager)) -> Any:
        result = dataloader.load_mo_address_types()
        return result

    # Get MO IT system types
    @app.get("/MO/IT_systems", status_code=202, tags=["MO"])
    async def load_it_systems_from_MO(user=Depends(login_manager)) -> Any:
        result = dataloader.load_mo_it_systems()
        return result

    return app
