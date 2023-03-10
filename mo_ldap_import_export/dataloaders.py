# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
"""Dataloaders to bulk requests."""
import datetime
from typing import Any
from typing import cast
from typing import Union
from uuid import UUID

import structlog
from gql import gql
from gql.client import AsyncClientSession
from gql.client import SyncClientSession
from gql.transport.exceptions import TransportQueryError
from graphql import DocumentNode
from ldap3.core.exceptions import LDAPInvalidValueError
from ldap3.protocol import oid
from ramodels.mo.details.address import Address
from ramodels.mo.details.engagement import Engagement
from ramodels.mo.details.it_system import ITUser
from ramodels.mo.employee import Employee
from ramqp.mo.models import ObjectType
from ramqp.mo.models import PayloadType
from ramqp.mo.models import ServiceType

from .exceptions import AttributeNotFound
from .exceptions import CprNoNotFound
from .exceptions import InvalidChangeDict
from .exceptions import InvalidQueryResponse
from .exceptions import MultipleObjectsReturnedException
from .exceptions import NoObjectsReturnedException
from .ldap import get_attribute_types
from .ldap import get_ldap_attributes
from .ldap import get_ldap_schema
from .ldap import get_ldap_superiors
from .ldap import make_ldap_object
from .ldap import paged_search
from .ldap import single_object_search
from .ldap_classes import LdapObject
from .utils import add_filter_to_query


class DataLoader:
    def __init__(self, context):
        self.logger = structlog.get_logger()
        self.context = context
        self.user_context = context["user_context"]
        self.ldap_connection = self.user_context["ldap_connection"]
        self.attribute_types = get_attribute_types(self.ldap_connection)
        self.single_value = {
            a: self.attribute_types[a].single_value for a in self.attribute_types.keys()
        }
        self._mo_to_ldap_attributes = []
        self._sync_tool = None

    def _check_if_empty(self, result: dict):
        for key, value in result.items():
            if len(value) == 0:
                raise NoObjectsReturnedException(
                    (
                        f"query_result['{key}'] is empty. "
                        "Does the object still exist as a current object?"
                    )
                )

    @property
    def sync_tool(self):
        if not self._sync_tool:
            self._sync_tool = self.user_context["sync_tool"]
        return self._sync_tool

    @property
    def mo_to_ldap_attributes(self):
        """
        Populates self._mo_to_ldap_attributes and returns it.

        self._mo_to_ldap_attributes is a list of all LDAP attribute names which
        are synchronized to LDAP

        Notes
        -------
        This is not done in __init__() because the converter is not initialized yet,
        when we initialize the dataloader.
        """
        if not self._mo_to_ldap_attributes:
            converter = self.user_context["converter"]
            for json_dict in converter.mapping["mo_to_ldap"].values():
                self._mo_to_ldap_attributes.extend(list(json_dict.keys()))
        return self._mo_to_ldap_attributes

    def shared_attribute(self, attribute: str):
        """
        Determine if an attribute is shared between multiple LDAP objects.

        Parameters
        ------------
        attribute : str
            LDAP attribute name

        Returns
        ----------
        return_value : bool
            True if the attribute is shared between different LDAP objects, False if it
            is not.

        Examples
        -----------
        >>> self.shared_attribute("cpr_no")
        >>> True

        The "cpr_no" attribute is generally shared between different LDAP objects.
        Therefore the return value is "True"

        >>> self.shared_attribute("mobile_phone_no")
        >>> False

        An attribute which contains a phone number is generally only used by a single
        LDAP object. Therefore the return value is "False"

        Notes
        -------
        The return value in above examples depends on the json dictionary.
        """
        occurences = self.mo_to_ldap_attributes.count(attribute)
        if occurences == 1:
            return False
        elif occurences > 1:
            return True
        else:
            raise AttributeNotFound(
                f"'{attribute}' not found in 'mo_to_ldap' attributes"
            )

    async def query_mo(
        self,
        query: DocumentNode,
        raise_if_empty: bool = True,
    ):
        graphql_session: AsyncClientSession = self.user_context["gql_client"]
        result = await graphql_session.execute(query)
        if raise_if_empty:
            self._check_if_empty(result)
        return result

    async def query_past_future_mo(
        self, query: DocumentNode, current_objects_only: bool
    ):
        """
        First queries MO. If no objects are returned, attempts to query past/future
        objects as well
        """
        try:
            return await self.query_mo(query)
        except NoObjectsReturnedException as e:
            if current_objects_only:
                raise e
            else:
                query = add_filter_to_query(query, "to_date: null, from_date: null")
                return await self.query_mo(query)

    def query_mo_sync(self, query, raise_if_empty=True):
        graphql_session: SyncClientSession = self.user_context["gql_client_sync"]
        result = graphql_session.execute(query)
        if raise_if_empty:
            self._check_if_empty(result)
        return result

    def load_ldap_object(self, dn, attributes, nest=True):
        searchParameters = {
            "search_base": dn,
            "search_filter": "(objectclass=*)",
            "attributes": attributes,
        }
        search_result = single_object_search(
            searchParameters, self.ldap_connection, exact_dn_match=True
        )
        return make_ldap_object(search_result, self.context, nest=nest)

    def load_ldap_cpr_object(self, cpr_no: str, json_key: str) -> LdapObject:
        """
        Loads an ldap object which can be found using a cpr number lookup

        Accepted json_keys are:
            - 'Employee'
            - a MO address type name
        """
        cpr_no = cpr_no.replace("-", "")
        cpr_field = self.user_context["cpr_field"]
        settings = self.user_context["settings"]

        search_base = settings.ldap_search_base
        converter = self.user_context["converter"]

        object_class = converter.find_ldap_object_class(json_key)
        attributes = converter.get_ldap_attributes(json_key)

        object_class_filter = f"objectclass={object_class}"
        cpr_filter = f"{cpr_field}={cpr_no}"

        searchParameters = {
            "search_base": search_base,
            "search_filter": f"(&({object_class_filter})({cpr_filter}))",
            "attributes": attributes,
        }
        search_result = single_object_search(searchParameters, self.ldap_connection)

        ldap_object: LdapObject = make_ldap_object(search_result, self.context)
        self.logger.info(f"Found {ldap_object.dn}")

        return ldap_object

    def modify_ldap(
        self,
        dn: str,
        changes: Union[
            dict[str, list[tuple[str, list[str]]]],
            dict[str, list[tuple[str, str]]],
        ],
    ):
        """
        Modifies LDAP and adds the dn to dns_to_ignore
        """
        # Checks
        attributes = list(changes.keys())
        if len(attributes) != 1:
            raise InvalidChangeDict("Exactly one attribute can be changed at the time")

        attribute = attributes[0]
        list_of_changes = changes[attribute]
        if len(list_of_changes) != 1:
            raise InvalidChangeDict("Exactly one change can be submitted at the time")

        value_to_modify = list_of_changes[0][1]
        ldap_command = list_of_changes[0][0]
        if type(value_to_modify) is list:
            if len(value_to_modify) == 1:
                value_to_modify = value_to_modify[0]
            elif len(value_to_modify) == 0:
                value_to_modify = ""
            else:
                raise InvalidChangeDict("Exactly one value can be changed at the time")

        # Compare to LDAP
        value_exists = self.ldap_connection.compare(dn, attribute, value_to_modify)

        # Modify LDAP
        if not value_exists or "DELETE" in ldap_command:
            self.logger.info(
                f"[modify_ldap] Uploading the following changes: {changes}"
            )
            self.ldap_connection.modify(dn, changes)
            response = self.ldap_connection.result
            self.logger.info(f"[modify_ldap] Response: {response}")

            # If successful, the importer should ignore this DN
            if response["description"] == "success":
                # Clean all old entries
                self.sync_tool.dns_to_ignore.clean()

                # Only add if nothing is there yet. Otherwise we risk adding an
                # ignore-command for every modified parameter
                #
                # Also: even if an LDAP object gets modified by us twice within a couple
                # of seconds, it should still only be ignored once; Because we only
                # retrieve the latest state of the LDAP object when polling
                if not self.sync_tool.dns_to_ignore[dn]:
                    self.sync_tool.dns_to_ignore.add(dn)

            return response
        else:
            self.logger.info(
                f"[modify_ldap] {attribute}['{value_to_modify}'] already exists"
            )

    def cleanup_attributes_in_ldap(self, ldap_objects: list[LdapObject]):
        """
        Deletes the values belonging to the attributes in the given ldap objects.

        Notes
        ----------
        Will not delete values belonging to attributes which are shared between multiple
        ldap objects. Because deleting an LDAP object should not remove the possibility
        to compile an LDAP object of a different type.
        """
        for ldap_object in ldap_objects:
            self.logger.info(f"Cleaning up attributes from {ldap_object.dn}")
            attributes_to_clean = [
                a
                for a in ldap_object.dict().keys()
                if a != "dn" and not self.shared_attribute(a)
            ]

            if not attributes_to_clean:
                self.logger.info("No cleanable attributes found")
                return

            dn = ldap_object.dn
            for attribute in attributes_to_clean:
                value_to_delete = ldap_object.dict()[attribute]
                self.logger.info(f"Cleaning {value_to_delete} from '{attribute}'")

                changes = {attribute: [("MODIFY_DELETE", value_to_delete)]}
                self.modify_ldap(dn, changes)

    async def load_ldap_objects(self, json_key: str) -> list[LdapObject]:
        """
        Returns list with desired ldap objects

        Accepted json_keys are:
            - 'Employee'
            - a MO address type name
        """
        converter = self.user_context["converter"]
        user_class = converter.find_ldap_object_class(json_key)
        attributes = converter.get_ldap_attributes(json_key)

        searchParameters = {
            "search_filter": f"(objectclass={user_class})",
            "attributes": attributes,
        }

        responses = paged_search(self.context, searchParameters)

        output: list[LdapObject]
        output = [make_ldap_object(r, self.context, nest=False) for r in responses]

        return output

    async def modify_ldap_object(
        self,
        object_to_modify: LdapObject,
        json_key: str,
        overwrite: bool = False,
        delete: bool = False,
    ):
        """
        Parameters
        -------------
        object_to_modify : LDAPObject
            object to upload to LDAP
        json_key : str
            json key to upload. e.g. 'Employee' or 'Engagement' or another key present
            in the json dictionary.
        overwrite: bool
            Set to True to overwrite contents in LDAP
        delete: bool
            Set to True to delete contents in LDAP, instead of creating/modifying them
        """
        converter = self.user_context["converter"]
        if not converter.__export_to_ldap__(json_key):
            self.logger.info(f"__export_to_ldap__ == False for json_key = '{json_key}'")
            return None
        success = 0
        failed = 0
        cpr_field = self.user_context["cpr_field"]

        object_class = converter.find_ldap_object_class(json_key)
        parameters_to_modify = list(object_to_modify.dict().keys())

        # Check if the cpr field is present
        if cpr_field not in parameters_to_modify:
            raise CprNoNotFound(f"cpr field '{cpr_field}' not found in ldap object")

        try:
            # Note: it is possible that an employee object exists, but that the CPR no.
            # attribute is not set. In that case this function will just set the cpr no.
            # attribute in LDAP.
            existing_object = self.load_ldap_cpr_object(
                object_to_modify.dict()[cpr_field], json_key
            )
            object_to_modify.dn = existing_object.dn
            self.logger.info(f"Found existing object: {existing_object.dn}")
        except NoObjectsReturnedException:
            self.logger.info("Could not find existing object: An entry will be created")

        self.logger.info(f"Uploading {object_to_modify}")
        parameters_to_modify = [p for p in parameters_to_modify if p != "dn"]
        dn = object_to_modify.dn
        results = []

        if delete:
            # Only delete parameters which are not shared between different objects.
            # For example: 'org-unit name' should not be deleted if both
            # engagements and org unit addresses use it;
            #
            # If we would delete 'org-unit name' as a part of an org-unit address delete
            # operation, We would suddenly not be able to import engagements any more.
            parameters_to_modify = [
                p for p in parameters_to_modify if not self.shared_attribute(p)
            ]

        for parameter_to_modify in parameters_to_modify:
            value = object_to_modify.dict()[parameter_to_modify]
            value_to_modify: list[str] = [] if value is None else [value]

            if delete:
                changes = {parameter_to_modify: [("MODIFY_DELETE", value_to_modify)]}
            elif self.single_value[parameter_to_modify] or overwrite:
                changes = {parameter_to_modify: [("MODIFY_REPLACE", value_to_modify)]}
            else:
                changes = {parameter_to_modify: [("MODIFY_ADD", value_to_modify)]}

            try:
                response = self.modify_ldap(dn, changes)
            except LDAPInvalidValueError as e:
                self.logger.warning(e)
                failed += 1
                continue

            # If the user does not exist, create him/her/hir
            if response and response["description"] == "noSuchObject":
                self.logger.info(f"Received 'noSuchObject' response. Creating {dn}")
                self.ldap_connection.add(dn, object_class)
                response = self.ldap_connection.result
                self.logger.info(f"Response: {response}")
                response = self.modify_ldap(dn, changes)

            if response and response["description"] == "success":
                success += 1
            elif response:
                failed += 1

            results.append(response)

        self.logger.info(f"Succeeded MODIFY_* operations: {success}")
        self.logger.info(f"Failed MODIFY_* operations: {failed}")
        return results

    def make_overview_entry(self, attributes, superiors, example_value_dict=None):

        attribute_dict = {}
        for attribute in attributes:
            syntax = self.attribute_types[attribute].syntax

            # decoded syntax tuple structure: (oid, kind, name, docs)
            syntax_decoded = oid.decode_syntax(syntax)
            details_dict = {
                "single_value": self.attribute_types[attribute].single_value,
                "syntax": syntax,
            }
            if syntax_decoded:
                details_dict["field_type"] = syntax_decoded[2]

            if example_value_dict:
                if attribute in example_value_dict:
                    details_dict["example_value"] = example_value_dict[attribute]

            attribute_dict[attribute] = details_dict

        return {
            "superiors": superiors,
            "attributes": attribute_dict,
        }

    def load_ldap_overview(self):
        schema = get_ldap_schema(self.ldap_connection)

        all_object_classes = sorted(list(schema.object_classes.keys()))

        output = {}
        for ldap_class in all_object_classes:
            all_attributes = get_ldap_attributes(self.ldap_connection, ldap_class)
            superiors = get_ldap_superiors(self.ldap_connection, ldap_class)
            output[ldap_class] = self.make_overview_entry(all_attributes, superiors)

        return output

    def load_ldap_populated_overview(self, ldap_classes=None):
        """
        Like load_ldap_overview but only returns fields which actually contain data
        """
        nan_values: list[Union[None, list]] = [None, []]

        output = {}
        overview = self.load_ldap_overview()

        if not ldap_classes:
            ldap_classes = overview.keys()

        for ldap_class in ldap_classes:
            searchParameters = {
                "search_filter": f"(objectclass={ldap_class})",
                "attributes": ["*"],
            }

            responses = paged_search(self.context, searchParameters)
            responses = [
                r
                for r in responses
                if r["attributes"]["objectClass"][-1].lower() == ldap_class.lower()
            ]

            populated_attributes = []
            example_value_dict = {}
            for response in responses:
                for attribute, value in response["attributes"].items():
                    if value not in nan_values:
                        populated_attributes.append(attribute)
                        if attribute not in example_value_dict:
                            example_value_dict[attribute] = value
            populated_attributes = list(set(populated_attributes))

            if len(populated_attributes) > 0:
                superiors = overview[ldap_class]["superiors"]
                output[ldap_class] = self.make_overview_entry(
                    populated_attributes, superiors, example_value_dict
                )

        return output

    def _return_mo_employee_uuid_result(self, result) -> Union[None, UUID]:
        if len(result["employees"]) == 0:
            return None
        else:
            uuid: UUID = result["employees"][0]["uuid"]
            return uuid

    async def find_mo_employee_uuid(self, cpr_no: str) -> Union[None, UUID]:
        query = gql(
            """
            query FindEmployeeUUID {
              employees(cpr_numbers: "%s") {
                uuid
              }
            }
            """
            % cpr_no.replace("-", "")
        )

        result = await self.query_mo(query, raise_if_empty=False)
        return self._return_mo_employee_uuid_result(result)

    def find_mo_employee_uuid_sync(self, cpr_no: str) -> Union[None, UUID]:
        query = gql(
            """
            query FindEmployeeUUID {
              employees(cpr_numbers: "%s") {
                uuid
              }
            }
            """
            % cpr_no.replace("-", "")
        )

        result = self.query_mo_sync(query, raise_if_empty=False)
        return self._return_mo_employee_uuid_result(result)

    async def load_mo_employee(self, uuid: UUID, current_objects_only=True) -> Employee:
        query = gql(
            """
            query SinlgeEmployee {
              employees(uuids:"%s") {
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

        result = await self.query_past_future_mo(query, current_objects_only)
        entry = result["employees"][0]["objects"][0]

        return Employee(**entry)

    async def load_mo_employees_in_org_unit(
        self, org_unit_uuid: UUID
    ) -> list[Employee]:
        """
        Load all current employees engaged to an org unit
        """
        query = gql(
            """
            query EmployeeOrgUnitUUIDs {
              org_units(uuids: "%s") {
                objects {
                  engagements {
                    employee_uuid
                  }
                }
              }
            }
            """
            % org_unit_uuid
        )

        result = await self.query_mo(query)
        output = []
        for engagement_entry in result["org_units"][0]["objects"][0]["engagements"]:
            employee = await self.load_mo_employee(engagement_entry["employee_uuid"])
            output.append(employee)
        return output

    def load_mo_facet(self, user_key) -> dict:
        query = gql(
            """
            query FacetQuery {
              facets(user_keys: "%s") {
                classes {
                  user_key
                  uuid
                  scope
                }
              }
            }
            """
            % user_key
        )
        result = self.query_mo_sync(query, raise_if_empty=False)

        if len(result["facets"]) == 0:
            output = {}
        else:
            output = {d["uuid"]: d for d in result["facets"][0]["classes"]}

        return output

    def load_mo_address_types(self) -> dict:
        employee_address_types = self.load_mo_facet("employee_address_type")
        org_unit_address_types = self.load_mo_facet("org_unit_address_type")
        return employee_address_types | org_unit_address_types

    def load_mo_job_functions(self) -> dict:
        return self.load_mo_facet("engagement_job_function")

    def load_mo_primary_types(self) -> dict:
        return self.load_mo_facet("primary_type")

    def load_mo_engagement_types(self) -> dict:
        return self.load_mo_facet("engagement_type")

    def load_mo_org_unit_types(self) -> dict:
        return self.load_mo_facet("org_unit_type")

    def load_mo_org_unit_levels(self) -> dict:
        return self.load_mo_facet("org_unit_level")

    def load_mo_it_systems(self) -> dict:
        query = gql(
            """
            query ItSystems {
              itsystems {
                uuid
                user_key
              }
            }
            """
        )
        result = self.query_mo_sync(query, raise_if_empty=False)

        if len(result["itsystems"]) == 0:
            output = {}
        else:
            output = {d["uuid"]: d for d in result["itsystems"]}

        return output

    def load_mo_org_units(self) -> dict:
        query = gql(
            """
            query OrgUnit {
              org_units {
                objects {
                  uuid
                  name
                  user_key
                  parent {
                    uuid
                    name
                  }
                }
              }
            }
            """
        )
        result = self.query_mo_sync(query, raise_if_empty=False)

        if len(result["org_units"]) == 0:
            output = {}
        else:
            output = {
                d["objects"][0]["uuid"]: d["objects"][0] for d in result["org_units"]
            }

        return output

    async def load_mo_it_user(self, uuid: UUID, current_objects_only=True):
        query = gql(
            """
            query MyQuery {
              itusers(uuids: "%s") {
                objects {
                  user_key
                  validity {
                    from
                    to
                  }
                  employee_uuid
                  itsystem_uuid
                }
              }
            }
            """
            % (uuid)
        )

        result = await self.query_past_future_mo(query, current_objects_only)
        entry = result["itusers"][0]["objects"][0]
        return ITUser.from_simplified_fields(
            user_key=entry["user_key"],
            itsystem_uuid=entry["itsystem_uuid"],
            from_date=entry["validity"]["from"],
            uuid=uuid,
            to_date=entry["validity"]["to"],
            person_uuid=entry["employee_uuid"],
        )

    async def load_mo_address(
        self, uuid: UUID, current_objects_only: bool = True
    ) -> Address:
        """
        Loads a mo address

        Notes
        ---------
        Only returns addresses which are valid today. Meaning the to/from date is valid.
        """
        query = gql(
            """
            query SingleAddress {
              addresses(uuids: "%s") {
                objects {
                  value: name
                  value2
                  uuid
                  visibility_uuid
                  employee_uuid
                  org_unit_uuid
                  person: employee {
                    cpr_no
                  }
                  validity {
                      from
                      to
                    }
                  address_type {
                      user_key
                      uuid}
                }
              }
            }
            """
            % (uuid)
        )

        self.logger.info(f"Loading address={uuid}")
        result = await self.query_past_future_mo(query, current_objects_only)

        entry = result["addresses"][0]["objects"][0]

        address = Address.from_simplified_fields(
            value=entry["value"],
            address_type_uuid=entry["address_type"]["uuid"],
            from_date=entry["validity"]["from"],
            uuid=entry["uuid"],
            to_date=entry["validity"]["to"],
            value2=entry["value2"],
            person_uuid=entry["employee_uuid"],
            visibility_uuid=entry["visibility_uuid"],
            org_unit_uuid=entry["org_unit_uuid"],
        )

        return address

    async def is_primary(self, engagement_uuid: UUID) -> bool:
        """
        Determine if an engagement is the primary engagement or not.
        """
        query = gql(
            """
            query IsPrimary {
              engagements(uuids: "%s") {
                objects {
                  is_primary
                }
              }
            }
            """
            % (engagement_uuid)
        )

        result = await self.query_mo(query)
        return True if result["engagements"][0]["objects"][0]["is_primary"] else False

    async def load_mo_engagement(
        self,
        uuid: UUID,
        current_objects_only: bool = True,
    ) -> Engagement:
        query = gql(
            """
            query SingleEngagement {
              engagements(uuids: "%s") {
                objects {
                  user_key
                  extension_1
                  extension_2
                  extension_3
                  extension_4
                  extension_5
                  extension_6
                  extension_7
                  extension_8
                  extension_9
                  extension_10
                  leave_uuid
                  primary_uuid
                  job_function_uuid
                  org_unit_uuid
                  engagement_type_uuid
                  employee_uuid
                  validity {
                    from
                    to
                  }
                }
              }
            }
            """
            % (uuid)
        )

        self.logger.info(f"Loading engagement={uuid}")
        result = await self.query_past_future_mo(query, current_objects_only)

        entry = result["engagements"][0]["objects"][0]

        engagement = Engagement.from_simplified_fields(
            org_unit_uuid=entry["org_unit_uuid"],
            person_uuid=entry["employee_uuid"],
            job_function_uuid=entry["job_function_uuid"],
            engagement_type_uuid=entry["engagement_type_uuid"],
            user_key=entry["user_key"],
            from_date=entry["validity"]["from"],
            to_date=entry["validity"]["to"],
            uuid=uuid,
            primary_uuid=entry["primary_uuid"],
            extension_1=entry["extension_1"],
            extension_2=entry["extension_2"],
            extension_3=entry["extension_3"],
            extension_4=entry["extension_4"],
            extension_5=entry["extension_5"],
            extension_6=entry["extension_6"],
            extension_7=entry["extension_7"],
            extension_8=entry["extension_8"],
            extension_9=entry["extension_9"],
            extension_10=entry["extension_10"],
        )
        return engagement

    async def load_mo_employee_addresses(
        self, employee_uuid, address_type_uuid
    ) -> list[Address]:
        """
        Loads all current addresses of a specific type for an employee
        """
        query = gql(
            """
            query GetEmployeeAddresses {
              employees(uuids: "%s") {
                objects {
                  addresses(address_types: "%s") {
                    uuid
                  }
                }
              }
            }
            """
            % (employee_uuid, address_type_uuid)
        )

        result = await self.query_mo(query)

        output = []
        for address_entry in result["employees"][0]["objects"][0]["addresses"]:
            address = await self.load_mo_address(address_entry["uuid"])
            output.append(address)
        return output

    async def load_mo_org_unit_addresses(
        self, org_unit_uuid, address_type_uuid
    ) -> list[Address]:
        """
        Loads all current addresses of a specific type for an org unit
        """
        query = gql(
            """
            query GetOrgUnitAddresses {
              org_units(uuids: "%s") {
                objects {
                  addresses(address_types: "%s") {
                    uuid
                  }
                }
              }
            }
            """
            % (org_unit_uuid, address_type_uuid)
        )

        result = await self.query_mo(query)

        output = []
        for address_entry in result["org_units"][0]["objects"][0]["addresses"]:
            address = await self.load_mo_address(address_entry["uuid"])
            output.append(address)
        return output

    async def load_mo_employee_it_users(self, employee_uuid, it_system_uuid):
        """
        Load all current it users of a specific type linked to an employee
        """
        query = gql(
            """
            query ItUserQuery {
              employees(uuids: "%s") {
                objects {
                  itusers {
                    uuid
                    itsystem_uuid
                  }
                }
              }
            }
            """
            % employee_uuid
        )

        result = await self.query_mo(query)

        output = []
        for it_user_dict in result["employees"][0]["objects"][0]["itusers"]:
            if it_user_dict["itsystem_uuid"] == str(it_system_uuid):
                it_user = await self.load_mo_it_user(it_user_dict["uuid"])
                output.append(it_user)
        return output

    async def load_mo_employee_engagements(
        self, employee_uuid: UUID
    ) -> list[Engagement]:
        """
        Load all current engagements linked to an employee
        """
        query = gql(
            """
            query EngagementQuery {
              employees(uuids: "%s") {
                objects {
                  engagements {
                    uuid
                  }
                }
              }
            }
            """
            % employee_uuid
        )

        result = await self.query_mo(query)

        output = []
        for engagement_dict in result["employees"][0]["objects"][0]["engagements"]:
            engagement = await self.load_mo_engagement(engagement_dict["uuid"])
            output.append(engagement)
        return output

    async def load_all_mo_objects(self, add_validity=False, uuid="") -> list[dict]:
        """
        Returns a list of dictionaries. One for each object in MO of one of the
        following types:
            - employee
            - org_unit
            - address (either employee or org unit addresses)
            - itusers
            - engagements

        Also adds AMQP object type, service type and payload to the dicts.

        If "uuid" is specified, only returns objects matching this uuid.
        """

        query_template = """
                         query AllObjects {
                             %s %s {
                                 objects {
                                     uuid
                                     %s
                                     %s
                                     }
                                 }
                             }
                         """

        if add_validity:
            validity_query = """
                             validity {
                                 from
                                 to
                             }
                             """
        else:
            validity_query = ""

        uuid_filter = f'(uuids: "{str(uuid)}")' if uuid else ""

        result: dict = {}
        warnings: list[str] = []
        for object_type in [
            "employees",
            "org_units",
            "addresses",
            "itusers",
            "engagements",
        ]:

            if object_type in ["employees", "org_units"]:
                additional_uuids = ""
            else:
                additional_uuids = """
                                   org_unit_uuid
                                   employee_uuid
                                   """

            query = gql(
                query_template
                % (object_type, uuid_filter, additional_uuids, validity_query)
            )

            try:
                sub_result = await self.query_mo(query, raise_if_empty=False)
                result = result | sub_result
            except TransportQueryError as e:
                warnings.append(str(e))

        if not result:
            for warning in warnings:
                self.logger.warning(warning)

        object_type_dict = {
            "employees": ObjectType.EMPLOYEE,
            "org_units": ObjectType.ORG_UNIT,
            "addresses": ObjectType.ADDRESS,
            "itusers": ObjectType.IT,
            "engagements": ObjectType.ENGAGEMENT,
        }

        output = []

        # Determine payload, service type, object type for use in amqp-messages
        for object_type, mo_object_dicts in result.items():
            for mo_object_dict in mo_object_dicts:
                mo_object = mo_object_dict["objects"][0]

                # Note that engagements have both employee_uuid and org_unit uuid. But
                # belong to an employee. We handle that by checking for employee_uuid
                # first
                if "employee_uuid" in mo_object and mo_object["employee_uuid"]:
                    parent_uuid = mo_object["employee_uuid"]
                    service_type = ServiceType.EMPLOYEE
                elif "org_unit_uuid" in mo_object and mo_object["org_unit_uuid"]:
                    parent_uuid = mo_object["org_unit_uuid"]
                    service_type = ServiceType.ORG_UNIT
                else:
                    parent_uuid = mo_object["uuid"]
                    if object_type == "employees":
                        service_type = ServiceType.EMPLOYEE
                    elif object_type == "org_units":
                        service_type = ServiceType.ORG_UNIT
                    else:
                        raise InvalidQueryResponse(
                            (
                                f"{mo_object} object type '{object_type}' is "
                                "neither 'employees' nor 'org_units'"
                            )
                        )

                mo_object["payload"] = PayloadType(
                    uuid=parent_uuid,
                    object_uuid=mo_object["uuid"],
                    time=datetime.datetime.now(),
                )

                mo_object["object_type"] = object_type_dict[object_type]
                mo_object["service_type"] = service_type

                output.append(mo_object)

        if uuid and len(output) > 1:
            raise MultipleObjectsReturnedException(
                f"Found multiple objects with uuid={uuid}"
            )

        return output

    async def load_mo_object(self, uuid: str, add_validity=False):
        """
        Returns a mo object as dictionary

        Notes
        -------
        returns None if the object is not a current object
        """
        mo_objects = await self.load_all_mo_objects(
            add_validity=add_validity,
            uuid=str(uuid),
        )
        if mo_objects:
            # Note: load_all_mo_objects checks if len==1
            return mo_objects[0]
        else:
            return None

    async def upload_mo_objects(self, objects: list[Any]):
        """
        Uploads a mo object.
            - If an Employee object is supplied, the employee is updated/created
            - If an Address object is supplied, the address is updated/created
            - And so on...
        """

        model_client = self.user_context["model_client"]
        return cast(list[Any | None], await model_client.upload(objects))
