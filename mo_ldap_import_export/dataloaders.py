# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
"""Dataloaders to bulk requests."""
from functools import partial
from typing import Any
from typing import Callable
from typing import cast
from typing import Union

import structlog
from fastramqpi.context import Context
from gql import gql
from gql.client import AsyncClientSession
from gql.client import SyncClientSession
from pydantic import BaseModel
from raclients.modelclient.mo import ModelClient
from ramodels.mo.details.address import Address
from ramodels.mo.employee import Employee
from strawberry.dataloader import DataLoader

from .exceptions import CprNoNotFound
from .exceptions import NoObjectsReturnedException
from .ldap import get_ldap_attributes
from .ldap import get_ldap_schema
from .ldap import get_ldap_superiors
from .ldap import make_ldap_object
from .ldap import paged_search
from .ldap import single_object_search
from .ldap_classes import LdapObject

json_key = str
cpr_no = str


class Dataloaders(BaseModel):
    """Collection of program dataloaders."""

    class Config:
        """Arbitrary types need to be allowed to have DataLoader members."""

        arbitrary_types_allowed = True

    ldap_objects_loader: DataLoader
    ldap_object_loader: DataLoader
    ldap_object_uploader: DataLoader

    mo_employee_uploader: DataLoader
    mo_employee_loader: DataLoader
    mo_address_loader: DataLoader
    mo_address_uploader: DataLoader

    ldap_overview_loader: DataLoader
    ldap_populated_overview_loader: DataLoader


async def load_ldap_cpr_object(
    keys: list[tuple[cpr_no, json_key]], context: Context
) -> list[LdapObject]:
    """
    Loads an ldap object which can be found using a cpr number lookup

    Accepted json_keys are:
        - Employee
        - a MO address type name
    """
    logger = structlog.get_logger()
    user_context = context["user_context"]

    ldap_connection = user_context["ldap_connection"]
    cpr_field = user_context["cpr_field"]
    settings = user_context["settings"]

    search_base = settings.ldap_search_base
    converter = user_context["converter"]

    output = []

    for cpr, json_key in keys:
        object_class = converter.find_ldap_object_class(json_key)
        attributes = converter.get_ldap_attributes(json_key)

        object_class_filter = f"objectclass={object_class}"
        cpr_filter = f"{cpr_field}={cpr}"

        searchParameters = {
            "search_base": search_base,
            "search_filter": f"(&({object_class_filter})({cpr_filter}))",
            "attributes": attributes,
        }
        search_result = single_object_search(searchParameters, ldap_connection)

        ldap_object: LdapObject = make_ldap_object(search_result, context)

        logger.info(f"Found {ldap_object.dn}")
        output.append(ldap_object)

    return output


async def load_ldap_objects(
    keys: list[json_key], context: Context
) -> list[list[LdapObject]]:
    """
    Returns list with all employees
    """

    user_context = context["user_context"]
    converter = user_context["converter"]
    json_key = keys[0]
    user_class = converter.find_ldap_object_class(json_key)
    attributes = converter.get_ldap_attributes(json_key)

    searchParameters = {
        "search_filter": f"(objectclass={user_class})",
        "attributes": attributes,
    }

    responses = paged_search(context, searchParameters)

    output: list[LdapObject]
    output = [make_ldap_object(r, context, nest=False) for r in responses]

    return [output]


async def upload_ldap_object(
    keys: list[tuple[LdapObject, json_key]],
    context: Context,
):
    """
    Accepted json_keys are:
        - Employee
        - a MO address type name
    """
    logger = structlog.get_logger()
    user_context = context["user_context"]
    ldap_connection = user_context["ldap_connection"]
    converter = user_context["converter"]
    output = []
    success = 0
    failed = 0
    cpr_field = user_context["cpr_field"]
    for object_to_upload, json_key in keys:
        object_class = converter.find_ldap_object_class(json_key)
        all_attributes = get_ldap_attributes(ldap_connection, object_class)

        logger.info(f"Uploading {object_to_upload}")
        parameters_to_upload = list(object_to_upload.dict().keys())

        # Check if the cpr field is present
        if cpr_field not in parameters_to_upload:
            raise CprNoNotFound(f"cpr field '{cpr_field}' not found in ldap object")

        try:
            existing_object = await load_ldap_cpr_object(
                [(object_to_upload.dict()[cpr_field], json_key)], context=context
            )
            dn = existing_object[0].dn
            logger.info(f"Found existing employee: {dn}")
        except NoObjectsReturnedException as e:
            logger.info(f"Could not find existing employee: {e}")

            # Note: it is possible that the employee exists, but that the CPR no.
            # attribute is not set. In that case this function will just set the cpr no.
            # attribute in LDAP.
            dn = object_to_upload.dn

        parameters_to_upload = [
            p for p in parameters_to_upload if p != "dn" and p in all_attributes
        ]
        results = []
        parameters = object_to_upload.dict()

        for parameter_to_upload in parameters_to_upload:
            value = parameters[parameter_to_upload]
            value_to_upload = [] if value is None else [value]
            changes = {parameter_to_upload: [("MODIFY_REPLACE", value_to_upload)]}

            logger.info(f"Uploading the following changes: {changes}")
            ldap_connection.modify(dn, changes)
            response = ldap_connection.result

            # If the user does not exist, create him/her/hir
            if response["description"] == "noSuchObject":
                logger.info(f"Creating {dn}")
                ldap_connection.add(dn, object_class)
                ldap_connection.modify(dn, changes)
                response = ldap_connection.result

            if response["description"] == "success":
                success += 1
            else:
                failed += 1
            logger.info(f"Response: {response}")

            results.append(response)

        output.append(results)

    logger.info(f"Succeeded MODIFY_REPLACE operations: {success}")
    logger.info(f"Failed MODIFY_REPLACE operations: {failed}")
    return output


def make_overview_entry(attributes, superiors):
    return {
        "attributes": attributes,
        "superiors": superiors,
    }


async def load_ldap_overview(keys: list[int], context: Context):
    user_context = context["user_context"]
    ldap_connection = user_context["ldap_connection"]
    schema = get_ldap_schema(ldap_connection)

    all_object_classes = sorted(list(schema.object_classes.keys()))

    output = {}
    for ldap_class in all_object_classes:
        all_attributes = get_ldap_attributes(ldap_connection, ldap_class)
        superiors = get_ldap_superiors(ldap_connection, ldap_class)
        output[ldap_class] = make_overview_entry(all_attributes, superiors)

    return [output]


async def load_ldap_populated_overview(keys: list[int], context: Context):
    """
    Like load_ldap_overview but only returns fields which actually contain data
    """
    nan_values: list[Union[None, list]] = [None, []]

    output = {}
    overview = (await load_ldap_overview([1], context))[0]

    for ldap_class in overview.keys():
        searchParameters = {
            "search_filter": f"(objectclass={ldap_class})",
            "attributes": ["*"],
        }

        responses = paged_search(context, searchParameters)

        populated_attributes = []
        for response in responses:
            for attribute, value in response["attributes"].items():
                if value not in nan_values:
                    populated_attributes.append(attribute)
        populated_attributes = list(set(populated_attributes))

        if len(populated_attributes) > 0:
            superiors = overview[ldap_class]["superiors"]
            output[ldap_class] = make_overview_entry(populated_attributes, superiors)

    return [output]


async def load_mo_employee(
    keys: list[str], graphql_session: AsyncClientSession
) -> list[Employee]:
    output = []
    for uuid in keys:
        query = gql(
            """
            query SinlgeEmployee {
              employees(uuids:"{%s}") {
                objects {
                    uuid
                    cpr_no
                    givenname
                    surname
                    nickname_givenname
                    nickname_surname
                }
              }
            }
            """
            % uuid
        )

        result = await graphql_session.execute(query)
        entry = result["employees"][0]["objects"][0]
        output.append(Employee(**entry))

    return output


def load_mo_address_types(user_context) -> dict:
    query = gql(
        """
        query AddressTypes {
          facets(user_keys: "employee_address_type") {
            classes {
              name
              uuid
            }
          }
        }
        """
    )

    graphql_session: SyncClientSession = user_context["gql_client_sync"]
    result = graphql_session.execute(query)

    output = {d["uuid"]: d["name"] for d in result["facets"][0]["classes"]}
    return output


async def load_mo_address(
    keys: list[str], graphql_session: AsyncClientSession
) -> list[tuple[Address, dict]]:
    output = []
    for uuid in keys:
        query = gql(
            """
            query SingleAddress {
              addresses(uuids: "{%s}") {
                objects {
                  name
                  uuid
                  employee {
                    cpr_no
                    uuid
                  }
                  validity {
                      from
                    }
                  address_type {
                      name
                      uuid}

                }
              }
            }
            """
            % (uuid)
        )

        result = await graphql_session.execute(query)
        entry = result["addresses"][0]["objects"][0]

        address = Address.from_simplified_fields(
            entry["name"],
            entry["address_type"]["uuid"],
            entry["validity"]["from"],
            person_uuid=entry["employee"][0]["uuid"],
            uuid=entry["uuid"],
        )

        # We make a dict with meta-data because ramodels Address does not support
        # (among others) address_type names. It only supports uuids
        address_metadata = {
            "address_type_name": entry["address_type"]["name"],
            "employee_cpr_no": entry["employee"][0]["cpr_no"],
        }

        output.append((address, address_metadata))

    return output


async def upload_mo_employee(
    keys: list[Employee],
    model_client: ModelClient,
):
    return cast(list[Any | None], await model_client.upload(keys))


async def upload_mo_address(
    keys: list[Address],
    model_client: ModelClient,
):
    return cast(list[Any | None], await model_client.upload(keys))


def configure_dataloaders(context: Context) -> Dataloaders:
    """Construct our dataloaders from the FastRAMQPI context.

    Args:
        context: The FastRAMQPI context to configure our dataloaders with.

    Returns:
        Dataloaders required
    """

    graphql_loader_functions: dict[str, Callable] = {
        "mo_employee_loader": load_mo_employee,
        "mo_address_loader": load_mo_address,
    }

    user_context = context["user_context"]
    graphql_session = user_context["gql_client"]
    graphql_dataloaders: dict[str, DataLoader] = {
        key: DataLoader(
            load_fn=partial(value, graphql_session=graphql_session), cache=False
        )
        for key, value in graphql_loader_functions.items()
    }

    model_client = user_context["model_client"]

    mo_uploader_functions: dict[str, Callable] = {
        "mo_employee_uploader": upload_mo_employee,
        "mo_address_uploader": upload_mo_address,
    }

    mo_uploaders: dict[str, DataLoader] = {
        key: DataLoader(
            load_fn=partial(value, model_client=model_client),
            cache=False,
        )
        for key, value in mo_uploader_functions.items()
    }

    ldap_loader_functions: dict[str, Callable] = {
        "ldap_objects_loader": load_ldap_objects,
        "ldap_object_loader": load_ldap_cpr_object,
        "ldap_object_uploader": upload_ldap_object,
        "ldap_overview_loader": load_ldap_overview,
        "ldap_populated_overview_loader": load_ldap_populated_overview,
    }

    ldap_dataloaders: dict[str, DataLoader] = {
        key: DataLoader(
            load_fn=partial(
                value,
                context=context,
            ),
            cache=False,
        )
        for key, value in ldap_loader_functions.items()
    }

    return Dataloaders(**graphql_dataloaders, **ldap_dataloaders, **mo_uploaders)
