# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
"""Dataloaders to bulk requests."""
from typing import Any
from typing import cast
from typing import Union
from uuid import UUID

import structlog
from gql import gql
from gql.client import AsyncClientSession
from gql.client import SyncClientSession
from ramodels.mo.details.address import Address
from ramodels.mo.employee import Employee

from .exceptions import CprNoNotFound
from .exceptions import NoObjectsReturnedException
from .ldap import get_attribute_types
from .ldap import get_ldap_attributes
from .ldap import get_ldap_schema
from .ldap import get_ldap_superiors
from .ldap import make_ldap_object
from .ldap import paged_search
from .ldap import single_object_search
from .ldap_classes import LdapObject


class DataLoader:
    def __init__(self, context):
        self.context = context
        self.user_context = context["user_context"]
        self.ldap_connection = self.user_context["ldap_connection"]
        self.attribute_types = get_attribute_types(self.ldap_connection)

    async def load_ldap_cpr_object(self, cpr_no: str, json_key: str) -> LdapObject:
        """
        Loads an ldap object which can be found using a cpr number lookup

        Accepted json_keys are:
            - 'Employee'
            - a MO address type name
        """
        logger = structlog.get_logger()
        context = self.context
        user_context = context["user_context"]

        ldap_connection = user_context["ldap_connection"]
        cpr_field = user_context["cpr_field"]
        settings = user_context["settings"]

        search_base = settings.ldap_search_base
        converter = user_context["converter"]

        object_class = converter.find_ldap_object_class(json_key)
        attributes = converter.get_ldap_attributes(json_key)

        object_class_filter = f"objectclass={object_class}"
        cpr_filter = f"{cpr_field}={cpr_no}"

        searchParameters = {
            "search_base": search_base,
            "search_filter": f"(&({object_class_filter})({cpr_filter}))",
            "attributes": attributes,
        }
        search_result = single_object_search(searchParameters, ldap_connection)

        ldap_object: LdapObject = make_ldap_object(search_result, context)
        logger.info(f"Found {ldap_object.dn}")

        return ldap_object

    async def load_ldap_objects(self, json_key: str) -> list[LdapObject]:
        """
        Returns list with desired ldap objects
        """
        context = self.context

        user_context = context["user_context"]
        converter = user_context["converter"]
        user_class = converter.find_ldap_object_class(json_key)
        attributes = converter.get_ldap_attributes(json_key)

        searchParameters = {
            "search_filter": f"(objectclass={user_class})",
            "attributes": attributes,
        }

        responses = paged_search(context, searchParameters)

        output: list[LdapObject]
        output = [make_ldap_object(r, context, nest=False) for r in responses]

        return output

    async def upload_ldap_object(self, object_to_upload, json_key):
        """
        Accepted json_keys are:
            - 'Employee'
            - a MO address type name
        """
        context = self.context
        logger = structlog.get_logger()
        user_context = context["user_context"]
        ldap_connection = user_context["ldap_connection"]
        converter = user_context["converter"]
        success = 0
        failed = 0
        cpr_field = user_context["cpr_field"]

        object_class = converter.find_ldap_object_class(json_key)
        all_attributes = get_ldap_attributes(ldap_connection, object_class)

        logger.info(f"Uploading {object_to_upload}")
        parameters_to_upload = list(object_to_upload.dict().keys())

        # Check if the cpr field is present
        if cpr_field not in parameters_to_upload:
            raise CprNoNotFound(f"cpr field '{cpr_field}' not found in ldap object")

        try:
            existing_object = await self.load_ldap_cpr_object(
                object_to_upload.dict()[cpr_field], json_key
            )
            dn = existing_object.dn
            logger.info(f"Found existing object: {dn}")
        except NoObjectsReturnedException as e:
            logger.info(f"Could not find existing object: {e}")

            # Note: it is possible that an employee object exists, but that the CPR no.
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

            single_value = self.attribute_types[parameter_to_upload].single_value
            if single_value:
                changes = {parameter_to_upload: [("MODIFY_REPLACE", value_to_upload)]}
            else:
                changes = {parameter_to_upload: [("MODIFY_ADD", value_to_upload)]}

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

        logger.info(f"Succeeded MODIFY_REPLACE operations: {success}")
        logger.info(f"Failed MODIFY_REPLACE operations: {failed}")
        return results

    def make_overview_entry(self, attributes, superiors):
        return {
            "attributes": attributes,
            "superiors": superiors,
            "attribute_types": {a: self.attribute_types[a] for a in attributes},
        }

    def load_ldap_overview(self):
        context = self.context
        user_context = context["user_context"]
        ldap_connection = user_context["ldap_connection"]
        schema = get_ldap_schema(ldap_connection)

        all_object_classes = sorted(list(schema.object_classes.keys()))

        output = {}
        for ldap_class in all_object_classes:
            all_attributes = get_ldap_attributes(ldap_connection, ldap_class)
            superiors = get_ldap_superiors(ldap_connection, ldap_class)
            output[ldap_class] = self.make_overview_entry(all_attributes, superiors)

        return output

    def load_ldap_populated_overview(self):
        """
        Like load_ldap_overview but only returns fields which actually contain data
        """
        nan_values: list[Union[None, list]] = [None, []]
        context = self.context

        output = {}
        overview = self.load_ldap_overview()

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
                output[ldap_class] = self.make_overview_entry(
                    populated_attributes, superiors
                )

        return output

    async def load_mo_employee(self, uuid: UUID) -> Employee:
        context = self.context
        graphql_session: AsyncClientSession = context["user_context"]["gql_client"]

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

        return Employee(**entry)

    def load_mo_address_types(self) -> dict:
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
        context = self.context

        graphql_session: SyncClientSession = context["user_context"]["gql_client_sync"]
        result = graphql_session.execute(query)

        output = {d["uuid"]: d["name"] for d in result["facets"][0]["classes"]}
        return output

    async def load_mo_address(self, uuid: UUID) -> tuple[Address, dict]:
        context = self.context

        graphql_session: AsyncClientSession = context["user_context"]["gql_client"]
        query = gql(
            """
            query SingleAddress {
              addresses(uuids: "{%s}") {
                objects {
                  value: name
                  uuid
                  person: employee {
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
            entry["value"],
            entry["address_type"]["uuid"],
            entry["validity"]["from"],
            person_uuid=entry["person"][0]["uuid"],
            uuid=entry["uuid"],
        )

        # We make a dict with meta-data because ramodels Address does not support
        # (among others) address_type names. It only supports uuids
        address_metadata = {
            "address_type_name": entry["address_type"]["name"],
            "employee_cpr_no": entry["person"][0]["cpr_no"],
        }

        return (address, address_metadata)

    async def upload_mo_objects(self, objects: list[Any]):
        """
        Uploads a mo object.
            - If an Employee object is supplied, the employee is updated/created
            - If an Address object is supplied, the address is updated/created
            - And so on...
        """
        context = self.context

        model_client = context["user_context"]["model_client"]
        return cast(list[Any | None], await model_client.upload(objects))
