# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
"""
Created on Fri Mar  3 09:46:15 2023

@author: nick
"""
import asyncio
from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from typing import Any
from uuid import UUID
from uuid import uuid4

import structlog
from fastramqpi.context import Context
from fastramqpi.ra_utils.transpose_dict import transpose_dict
from fastramqpi.ramqp.depends import handle_exclusively_decorator
from fastramqpi.ramqp.mo import MORoutingKey
from fastramqpi.ramqp.utils import RequeueMessage
from httpx import HTTPStatusError
from more_itertools import all_equal
from more_itertools import first
from more_itertools import one
from more_itertools import quantify
from pydantic import parse_obj_as
from ramodels.mo import MOBase

from .converters import LdapConverter
from .customer_specific_checks import ExportChecks
from .customer_specific_checks import ImportChecks
from .dataloaders import DataLoader
from .dataloaders import DNList
from .dataloaders import Verb
from .exceptions import DNNotFound
from .exceptions import IgnoreChanges
from .exceptions import NoObjectsReturnedException
from .exceptions import NotSupportedException
from .ldap import cleanup
from .ldap_classes import LdapObject
from .utils import extract_ou_from_dn
from .utils import get_object_type_from_routing_key

logger = structlog.stdlib.get_logger()


class IgnoreMe:
    def __init__(self):
        self.ignore_dict: dict[str, list[datetime]] = {}

    def __getitem__(self, key: str | UUID) -> list[datetime]:
        key = self.format_entry(key)
        return self.ignore_dict.get(key, [])

    def __len__(self):
        return len(self.ignore_dict)

    def format_entry(self, entry: str | UUID) -> str:
        if not isinstance(entry, str):
            entry = str(entry)
        return entry.lower()

    def clean(self):
        # Remove all timestamps which have been in the ignore dict for more than 60 sec.
        now = datetime.now()
        max_age = 60  # seconds
        cutoff = now - timedelta(seconds=max_age)
        for str_to_ignore, timestamps in self.ignore_dict.items():
            for timestamp in timestamps.copy():
                if timestamp < cutoff:
                    logger.info(
                        "Removing entry from ignore-dict",
                        timestamp=timestamp,
                        str_to_ignore=str_to_ignore,
                        max_age=max_age,
                    )
                    timestamps.remove(timestamp)

        # Remove keys with empty lists
        self.ignore_dict = {k: v for k, v in self.ignore_dict.items() if v}

    def add(self, str_to_add: str | UUID):
        # Add a string to the ignore dict
        str_to_add = self.format_entry(str_to_add)

        if str_to_add in self.ignore_dict:
            self.ignore_dict[str_to_add].append(datetime.now())
        else:
            self.ignore_dict[str_to_add] = [datetime.now()]

    def remove(self, str_to_remove: str | UUID):
        str_to_remove = self.format_entry(str_to_remove)

        if str_to_remove in self.ignore_dict:
            # Remove latest entry from the ignore dict
            newest_timestamp = max(self.ignore_dict[str_to_remove])
            self.ignore_dict[str_to_remove].remove(newest_timestamp)

    def check(self, str_to_check: str | UUID):
        # Raise ignoreChanges if the string to check is in self.ignore_dict
        str_to_check = self.format_entry(str_to_check)
        self.clean()

        if str_to_check in self.ignore_dict and self.ignore_dict[str_to_check]:
            # Remove timestamp so it does not get ignored twice.
            oldest_timestamp = min(self.ignore_dict[str_to_check])
            self.ignore_dict[str_to_check].remove(oldest_timestamp)
            raise IgnoreChanges(f"Ignoring {str_to_check}")


class SyncTool:
    def __init__(self, context: Context):
        # UUIDs in this list will be ignored by listen_to_changes ONCE
        self.uuids_to_ignore = IgnoreMe()
        self.dns_to_ignore = IgnoreMe()

        self.context = context
        self.user_context = self.context["user_context"]
        self.dataloader: DataLoader = self.user_context["dataloader"]
        self.converter: LdapConverter = self.user_context["converter"]
        self.export_checks: ExportChecks = self.user_context["export_checks"]
        self.import_checks: ImportChecks = self.user_context["import_checks"]
        self.settings = self.user_context["settings"]
        self.amqpsystem = self.context["amqpsystem"]

    @staticmethod
    def wait_for_export_to_finish(func: Callable):
        """Runs the function while ensuring sequentiality w.r.t. the uuid parameter."""

        def extract_uuid(obj) -> UUID:
            """
            Extract an uuid from an object and return it

            Parameters
            -------------
            obj: Any
                Object which is either an uuid or an object with an uuid attribute
            """
            uuid = getattr(obj, "uuid", obj)
            if not isinstance(uuid, UUID):
                raise TypeError(f"{uuid} is not an uuid")
            return uuid

        def uuid_extractor(self, *args, **kwargs) -> UUID:
            uuid = extract_uuid(args[0] if args else kwargs["uuid"])
            logger.info("Generating UUID", uuid=str(uuid))
            return uuid

        return handle_exclusively_decorator(uuid_extractor)(func)

    @staticmethod
    def wait_for_import_to_finish(func: Callable):
        """Runs the function while ensuring sequentiality w.r.t. the dn parameter."""

        def dn_extractor(self, *args, **kwargs):
            dn = args[0] if args else kwargs["dn"]
            logger.info("Generating DN", dn=dn)
            return dn

        return handle_exclusively_decorator(dn_extractor)(func)

    async def perform_export_checks(self, employee_uuid: UUID, object_uuid: UUID):
        """
        Perform a number of customer-specific checks. Raising IgnoreChanges() if a
        check fails
        """

        if self.settings.check_alleroed_sd_number:
            # Check that an SD-employee number does not start with 9
            # If it does, rejectMessage is raised.
            await self.export_checks.check_alleroed_sd_number(
                employee_uuid,
                object_uuid,
            )

        # Check that the employee has an it-user with user_key = it_user_to_check
        await self.export_checks.check_it_user(
            employee_uuid,
            self.settings.it_user_to_check,
        )

    async def perform_import_checks(self, dn: str, json_key: str) -> bool:
        if self.settings.check_holstebro_ou_issue_57426:
            return await self.import_checks.check_holstebro_ou_is_externals_issue_57426(
                self.settings.check_holstebro_ou_issue_57426,
                dn,
                json_key,
            )
        return True

    def cleanup_needed(self, ldap_modify_responses: list[dict]):
        """
        If nothing was modified in LDAP, we also do not need to clean up.
        """
        for response in ldap_modify_responses:
            if response and response["description"] == "success":
                return True

        logger.info("No cleanup needed")
        return False

    def move_ldap_object(self, ldap_object: LdapObject, dn: str) -> LdapObject:
        """
        Parameters
        ----------------
        ldap_object: LdapObject
            LDAP object as converted by converter.to_ldap()
        dn: str
            DN which we expect the object to have

        Notes
        -----------
        If the DN on the ldap object is different from the supplied dn, we move the
        object in LDAP, so the two match. We always assume that the DN on the LDAP
        object is correct, because that one is mapped in the json file.
        """
        old_dn = dn
        new_dn = ldap_object.dn

        if new_dn == old_dn:
            return ldap_object

        old_ou = extract_ou_from_dn(old_dn)
        new_ou = extract_ou_from_dn(new_dn)

        logger.info(
            "Moving user to new organizational unit",
            old_ou=old_ou,
            new_ou=new_ou,
            old_dn=old_dn,
            new_dn=new_dn,
        )

        # Create the new OU (dataloader.create_ou checks if it exists)
        self.dataloader.create_ou(new_ou)

        # Move the object to the proper OU
        move_successful: bool = self.dataloader.move_ldap_object(old_dn, new_dn)

        if move_successful:
            # Delete the old OU (dataloader.delete_ou checks if it is empty)
            self.dataloader.delete_ou(old_ou)
        else:
            ldap_object.dn = old_dn

        return ldap_object

    @wait_for_export_to_finish
    async def listen_to_changes_in_employees(
        self,
        uuid: UUID,
        object_uuid: UUID,
        routing_key: MORoutingKey,
        delete: bool,
        current_objects_only: bool,
    ) -> None:
        """
        Parameters
        ---------------
        uuid: UUID
            uuid of the changed employee
        object_uuid: UUID
            uuid of the changed object, belonging to the changed employee
        routing_key: MoRoutingKey
            Routing key of the AMQP message
        delete: bool
            Whether to delete the object or not
        current_objects_only: bool
            Whether to load currently valid objects only or not
        """
        logger_args = {
            "uuid": str(uuid),
            "object_uuid": str(object_uuid),
            "routing_key": routing_key,
            "delete": delete,
        }

        logger.info(
            "Registered change in an employee",
            **logger_args,
        )

        # If the object was uploaded by us, it does not need to be synchronized.
        # Note that this is not necessary in listen_to_changes_in_org_units. Because
        # those changes potentially map to multiple employees
        try:
            self.uuids_to_ignore.check(object_uuid)
        except IgnoreChanges:
            logger.info("Ignoring UUID", exc_info=True)
            return
        await self.perform_export_checks(uuid, object_uuid)

        try:
            dns: DNList = await self.dataloader.find_or_make_mo_employee_dn(uuid)
        except DNNotFound:
            logger.info("DN not found", **logger_args)
            return

        # Get MO employee
        changed_employee = await self.dataloader.load_mo_employee(
            uuid,
            current_objects_only=current_objects_only,
        )
        logger.info(
            "Found Employee in MO",
            changed_employee=changed_employee,
            **logger_args,
        )

        mo_object_dict: dict[str, Any] = {"mo_employee": changed_employee}
        object_type = get_object_type_from_routing_key(routing_key)

        if object_type == "person":
            for dn in dns:
                # Convert to LDAP
                ldap_employee = await self.converter.to_ldap(
                    mo_object_dict, "Employee", dn
                )
                ldap_employee = self.move_ldap_object(ldap_employee, dn)

                # Upload to LDAP - overwrite because all employee fields are unique.
                # One person cannot have multiple names.
                await self.dataloader.modify_ldap_object(
                    ldap_employee,
                    "Employee",
                    overwrite=True,
                    delete=delete,
                )

        elif object_type == "address":
            # Get MO address
            changed_address = await self.dataloader.load_mo_address(
                object_uuid,
                current_objects_only=current_objects_only,
            )
            address_type_uuid = str(changed_address.address_type.uuid)
            json_key = await self.converter.get_employee_address_type_user_key(
                address_type_uuid
            )

            logger.info(
                "Obtained address",
                user_key=json_key,
                **logger_args,
            )
            mo_object_dict["mo_employee_address"] = changed_address

            # Convert & Upload to LDAP
            affected_dn = await self.dataloader.find_dn_by_engagement_uuid(
                uuid, changed_address.engagement, dns
            )
            ldap_object = await self.converter.to_ldap(
                mo_object_dict, json_key, affected_dn
            )
            ldap_object = self.move_ldap_object(ldap_object, affected_dn)

            ldap_modify_responses = await self.dataloader.modify_ldap_object(
                ldap_object,
                json_key,
                delete=delete,
            )

            if self.cleanup_needed(ldap_modify_responses):
                addresses_in_mo = await self.dataloader.load_mo_employee_addresses(
                    changed_employee.uuid, changed_address.address_type.uuid
                )

                await cleanup(
                    json_key,
                    "mo_employee_address",
                    addresses_in_mo,
                    self.user_context,
                    changed_employee,
                    object_type,
                    ldap_object.dn,
                )

        elif object_type == "ituser":
            # Get MO IT-user
            changed_it_user = await self.dataloader.load_mo_it_user(
                object_uuid,
                current_objects_only=current_objects_only,
            )
            it_system_type_uuid = changed_it_user.itsystem.uuid
            json_key = await self.converter.get_it_system_user_key(
                str(it_system_type_uuid)
            )

            logger.info(
                "Obtained IT system",
                user_key=json_key,
                **logger_args,
            )
            mo_object_dict["mo_employee_it_user"] = changed_it_user

            # Convert & Upload to LDAP
            affected_dn = await self.dataloader.find_dn_by_engagement_uuid(
                uuid, changed_it_user.engagement, dns
            )
            ldap_object = await self.converter.to_ldap(
                mo_object_dict, json_key, affected_dn
            )
            ldap_object = self.move_ldap_object(ldap_object, affected_dn)

            ldap_modify_responses = await self.dataloader.modify_ldap_object(
                ldap_object,
                json_key,
                delete=delete,
            )

            if self.cleanup_needed(ldap_modify_responses):
                # Load IT users belonging to this employee
                it_users_in_mo = await self.dataloader.load_mo_employee_it_users(
                    changed_employee.uuid, it_system_type_uuid
                )

                await cleanup(
                    json_key,
                    "mo_employee_it_user",
                    it_users_in_mo,
                    self.user_context,
                    changed_employee,
                    object_type,
                    ldap_object.dn,
                )

        elif object_type == "engagement":
            # Get MO Engagement
            changed_engagement = await self.dataloader.load_mo_engagement(
                object_uuid,
                current_objects_only=current_objects_only,
            )

            json_key = "Engagement"
            mo_object_dict["mo_employee_engagement"] = changed_engagement

            # Convert & Upload to LDAP
            # We upload an engagement to LDAP regardless of its 'primary' attribute.
            # Because it looks like you cannot set 'primary' when creating an engagement
            # in the OS2mo GUI.
            affected_dn = await self.dataloader.find_dn_by_engagement_uuid(
                uuid, changed_engagement, dns
            )
            ldap_object = await self.converter.to_ldap(
                mo_object_dict, json_key, affected_dn
            )
            ldap_object = self.move_ldap_object(ldap_object, affected_dn)
            ldap_modify_responses = await self.dataloader.modify_ldap_object(
                ldap_object,
                json_key,
                delete=delete,
            )

            if self.cleanup_needed(ldap_modify_responses):
                engagements_in_mo = await self.dataloader.load_mo_employee_engagements(
                    changed_employee.uuid
                )

                await cleanup(
                    json_key,
                    "mo_employee_engagement",
                    engagements_in_mo,
                    self.user_context,
                    changed_employee,
                    object_type,
                    ldap_object.dn,
                )

    @wait_for_export_to_finish
    async def process_employee_address(
        self,
        affected_employee,
        org_unit_uuid,
        changed_address,
        json_key,
        delete,
        object_type,
    ):
        await self.perform_export_checks(affected_employee.uuid, changed_address.uuid)
        dns: DNList = await self.dataloader.find_or_make_mo_employee_dn(
            affected_employee.uuid
        )

        mo_object_dict = {
            "mo_employee": affected_employee,
            "mo_org_unit_address": changed_address,
        }

        for dn in dns:
            # Convert & Upload to LDAP
            ldap_object = await self.converter.to_ldap(mo_object_dict, json_key, dn)
            ldap_object = self.move_ldap_object(ldap_object, dn)

            ldap_modify_responses = await self.dataloader.modify_ldap_object(
                ldap_object,
                json_key,
                delete=delete,
            )

            if self.cleanup_needed(ldap_modify_responses):
                addresses_in_mo = await self.dataloader.load_mo_org_unit_addresses(
                    org_unit_uuid, changed_address.address_type.uuid
                )

                await cleanup(
                    json_key,
                    "mo_org_unit_address",
                    addresses_in_mo,
                    self.user_context,
                    affected_employee,
                    object_type,
                    ldap_object.dn,
                )

    async def publish_engagements_for_org_unit(self, org_unit_uuid: UUID) -> None:
        """Publish events for all engagements attached to an org unit.

        Args:
            org_unit_uuid: UUID of the org-unit for which to publish messages.
        """
        await self.dataloader.graphql_client.org_unit_engagements_refresh(
            self.amqpsystem.exchange_name, org_unit_uuid
        )

    async def refresh_org_unit_info_cache(self) -> None:
        # When an org-unit is changed we need to update the org unit info. So we
        # know the new name of the org unit in case it was changed
        logger.info("Updating org unit info")
        self.converter.org_unit_info = await self.dataloader.load_mo_org_units()
        self.converter.check_org_unit_info_dict()

    @wait_for_export_to_finish
    async def listen_to_changes_in_org_units(
        self,
        uuid: UUID,
        object_uuid: UUID,
        routing_key: MORoutingKey,
        delete: bool,
        current_objects_only: bool,
    ) -> None:
        """
        Parameters
        ---------------
        uuid: UUID
            uuid of the changed org-unit
        object_uuid: UUID
            uuid of the changed object, belonging to the changed org-unit
        routing_key: MoRoutingKey
            Routing key of the AMQP message
        delete: bool
            Whether to delete the object or not
        current_objects_only: bool
            Whether to load currently valid objects only or not
        """

        logger_args = {
            "uuid": str(uuid),
            "object_uuid": str(object_uuid),
            "routing_key": routing_key,
            "delete": delete,
        }

        logger.info(
            "Registered change in an org_unit",
            current_objects_only=current_objects_only,
            **logger_args,
        )

        object_type = get_object_type_from_routing_key(routing_key)
        assert object_type == "address"
        # Get MO address
        changed_address = await self.dataloader.load_mo_address(
            object_uuid,
            current_objects_only=current_objects_only,
        )
        address_type_uuid = str(changed_address.address_type.uuid)
        json_key = await self.converter.get_org_unit_address_type_user_key(
            address_type_uuid
        )

        logger.info(
            "Obtained address",
            user_key=json_key,
            **logger_args,
        )

        ldap_object_class = self.converter.find_ldap_object_class(json_key)
        employee_object_class = self.converter.find_ldap_object_class("Employee")

        if ldap_object_class != employee_object_class:
            raise NotSupportedException(
                "Mapping organization unit addresses "
                "to non-employee objects is not supported"
            )

        affected_employees = set(
            await self.dataloader.load_mo_employees_in_org_unit(uuid)
        )
        logger.info(
            "Looping over 'n' employees",
            n=len(affected_employees),
            **logger_args,
        )

        for affected_employee in affected_employees:
            try:
                await self.process_employee_address(
                    affected_employee,
                    uuid,
                    changed_address,
                    json_key,
                    delete,
                    object_type,
                )
            except DNNotFound:
                logger.info("DNNotFound Exception", exc_info=True, **logger_args)
                continue
            except IgnoreChanges:
                logger.info("IgnoreChanges Exception", exc_info=True, **logger_args)
                continue

    async def format_converted_objects(
        self,
        converted_objects,
        json_key,
    ) -> list[tuple[MOBase, Verb]]:
        """
        for Address and Engagement objects:
            Loops through the objects, and sets the uuid if an existing matching object
            is found
        for ITUser objects:
            Loops through the objects and removes it if an existing matchin object is
            found
        for all other objects:
            returns the input list of converted_objects
        """

        mo_object_class = self.converter.find_mo_object_class(json_key).split(".")[-1]
        objects_in_mo: list[Any] = []

        # Load addresses already in MO
        if mo_object_class == "Address":
            assert all_equal([obj.person for obj in converted_objects])
            person = first(converted_objects).person

            assert all_equal([obj.org_unit for obj in converted_objects])
            org_unit = first(converted_objects).org_unit

            assert all_equal([obj.address_type for obj in converted_objects])
            address_type = first(converted_objects).address_type

            if person:
                objects_in_mo = await self.dataloader.load_mo_employee_addresses(
                    person.uuid,
                    address_type.uuid,
                )
            elif org_unit:
                objects_in_mo = await self.dataloader.load_mo_org_unit_addresses(
                    org_unit.uuid,
                    address_type.uuid,
                )
            else:
                logger.info(
                    "Could not format converted "
                    "objects: An address needs to have either a person uuid "
                    "OR an org unit uuid"
                )
                return []

            # TODO: It seems weird to match addresses by value, as value is likely to
            #       change quite often. Omada simply deletes and recreates addresses.
            #       Maybe we should consider doing the same here?
            value_key = "value"

        # Load engagements already in MO
        elif mo_object_class == "Engagement":
            assert all_equal([obj.person for obj in converted_objects])
            person = first(converted_objects).person

            objects_in_mo = await self.dataloader.load_mo_employee_engagements(
                person.uuid
            )
            value_key = "user_key"
            user_keys = [o.user_key for o in objects_in_mo]

            # If we have duplicate user_keys, remove those which are the same as the
            # primary engagement's user_key
            if len(set(user_keys)) < len(user_keys):
                primaries = await self.dataloader.is_primaries(
                    [o.uuid for o in objects_in_mo]
                )
                num_primaries = quantify(primaries)
                if num_primaries > 1:
                    raise RequeueMessage(
                        "Waiting for multiple primary engagements to be resolved"
                    )
                # TODO: if num_primaries == 0, we cannot remove duplicates, is this a problem?

                if num_primaries == 1:
                    primary_engagement = objects_in_mo[primaries.index(True)]
                    logger.info(
                        "Found primary engagement",
                        uuid=str(primary_engagement.uuid),
                        user_key=primary_engagement.user_key,
                    )
                    logger.info("Removing engagements with identical user keys")
                    objects_in_mo = [
                        o
                        for o in objects_in_mo
                        # Keep the primary engagement itself
                        if o == primary_engagement
                        # But remove duplicate user-key engagements
                        or o.user_key != primary_engagement.user_key
                    ]

        elif mo_object_class == "ITUser":
            assert all_equal([obj.person for obj in converted_objects])
            person = first(converted_objects).person

            assert all_equal([obj.itsystem for obj in converted_objects])
            itsystem = first(converted_objects).itsystem

            objects_in_mo = await self.dataloader.load_mo_employee_it_users(
                person.uuid, itsystem.uuid
            )

            value_key = "user_key"

        else:
            return [
                (converted_object, Verb.CREATE)
                for converted_object in converted_objects
            ]

        # Construct a map from value-key to list of matching objects
        values_in_mo = transpose_dict({a: getattr(a, value_key) for a in objects_in_mo})
        mo_attributes = set(self.converter.get_mo_attributes(json_key))

        # Set uuid if a matching one is found. so an object gets updated
        # instead of duplicated
        # TODO: Consider partitioning converted_objects before-hand
        operations = []
        for converted_object in converted_objects:
            converted_object_value = getattr(converted_object, value_key)

            values = values_in_mo.get(converted_object_value)
            # Either None or empty list means no match
            if not values:  # pragma: no cover
                # No match means we are creating a new object
                operations.append((converted_object, Verb.CREATE))
                continue
            # Multiple values means that it is ambiguous
            if len(values) > 1:  # pragma: no cover
                # Ambigious match means we do nothing
                # TODO: Should this really throw a RequeueMessage?
                logger.warning(
                    "Could not determine MO object bijection, skipping",
                    json_key=json_key,
                    value_key=value_key,
                    converted_object_value=converted_object_value,
                )
                continue
            # Exactly 1 match found
            logger.info(
                "Found matching key",
                json_key=json_key,
                value=getattr(converted_object, value_key),
            )

            matching_object = one(values)
            mo_object_dict_to_upload = matching_object.dict()

            converted_mo_object_dict = converted_object.dict()

            # TODO: We always used the matched UUID, even if we have one templated out?
            #       Is this the desired behavior, if I template an UUID I would have
            #       imagined that I would only ever touch the object with that UUID?
            mo_attributes = mo_attributes - {"validity", "uuid", "objectClass"}
            # Only copy over keys that exist in both sets
            mo_attributes = mo_attributes & converted_mo_object_dict.keys()

            for key in mo_attributes:
                logger.info(
                    "Setting value on upload dict",
                    key=key,
                    value=converted_mo_object_dict[key],
                )
                mo_object_dict_to_upload[key] = converted_mo_object_dict[key]

            mo_class = self.converter.import_mo_object_class(json_key)
            converted_object_uuid_checked = mo_class(**mo_object_dict_to_upload)

            # TODO: Try to get this reactivated, see: 87683a2b
            # # If an object is identical to the one already there, it does not need
            # # to be uploaded.
            # if converted_object_uuid_checked == matching_object:
            #     logger.info(
            #         "Converted object is identical "
            #         "to existing object, skipping"
            #     )
            #     continue
            # We found a match, so we are editing the object we matched
            operations.append((converted_object_uuid_checked, Verb.EDIT))

        return operations

    @wait_for_import_to_finish
    async def import_single_user(self, dn: str, force=False, manual_import=False):
        """
        Imports a single user from LDAP

        Parameters
        ----------------
        force : bool
            Can be set to 'True' to force import a user. Meaning that we do not check
            if the dn is in self.dns_to_ignore.
        """
        try:
            if not force:
                self.dns_to_ignore.check(dn)
        except IgnoreChanges:
            logger.info("IgnoreChanges Exception", exc_info=True, dn=dn)
            return

        logger.info(
            "Importing user",
            dn=dn,
            force=force,
            manual_import=manual_import,
        )

        # Get the employee's uuid (if he exists)
        # Note: We could optimize this by loading all relevant employees once. But:
        # - What if an employee is created by someone else while this code is running?
        # - We don't need the additional speed. This is meant as a one-time import
        # - We won't gain much; This is an asynchronous request. The code moves on while
        #   we are waiting for MO's response
        employee_uuid = await self.dataloader.find_mo_employee_uuid(dn)
        if not employee_uuid:
            logger.info(
                "Employee not found in MO",
                task="generating employee uuid",
                dn=dn,
            )
            employee_uuid = uuid4()

        # Get the employee's engagement UUID (for the engagement matching the employee's
        # AD ObjectGUID.) This depends on whether the "ADGUID" field mapping is set up
        # to map the engagement UUID into MO, so that when `import_single_user` creates
        # or updates a MO `ITUser` for "ADGUID", the relevant engagement UUID is used.
        engagement_uuid: UUID | None = await self.dataloader.find_mo_engagement_uuid(dn)
        if engagement_uuid is None:
            logger.info(
                "Engagement UUID not found in MO",
                dn=dn,
            )
        else:
            logger.info(
                "Engagement UUID found in MO",
                engagement_uuid=engagement_uuid,
                dn=dn,
            )

        # First import the Employee, then Engagement if present, then the rest.
        # We want this order so dependencies exist before their dependent objects
        # TODO: Maybe there should be a dependency graph in the future
        detected_json_keys = set(self.converter.get_ldap_to_mo_json_keys())
        # We always want Employee in our json_keys
        detected_json_keys.add("Employee")
        priority_map = {"Employee": 1, "Engagement": 2}
        json_keys = sorted(detected_json_keys, key=lambda x: priority_map.get(x, 3))

        json_keys = [
            json_key
            for json_key in json_keys
            if await self.perform_import_checks(dn, json_key)
        ]
        logger.info("Import checks executed", json_keys=json_keys)

        json_keys = [
            json_key
            for json_key in json_keys
            if self.converter._import_to_mo_(json_key, manual_import)
        ]
        logger.info("Import to MO filtered", json_keys=json_keys)

        for json_key in json_keys:
            updated_engagement_uuid = await self.import_single_user_entity(
                json_key, dn, employee_uuid, engagement_uuid
            )
            engagement_uuid = updated_engagement_uuid or engagement_uuid

    async def import_single_user_entity(
        self, json_key: str, dn: str, employee_uuid: UUID, engagement_uuid: UUID | None
    ) -> UUID | None:
        logger.info("Loading object", dn=dn, json_key=json_key)
        loaded_object = self.dataloader.load_ldap_object(
            dn,
            self.converter.get_ldap_attributes(json_key),
        )
        logger.info(
            "Loaded object",
            dn=dn,
            json_key=json_key,
            loaded_object=loaded_object,
        )

        converted_objects = await self.converter.from_ldap(
            loaded_object,
            json_key,
            employee_uuid=employee_uuid,
            engagement_uuid=engagement_uuid,
        )
        if not converted_objects:
            logger.info("No converted objects", dn=dn)
            return engagement_uuid

        logger.info(
            "Converted 'n' objects ",
            n=len(converted_objects),
            dn=dn,
        )

        # In case the engagement does not exist yet
        if json_key == "Engagement":
            # TODO: Why are we extracting the first object as opposed to the last?
            engagement_uuid = first(converted_objects).uuid
            logger.info(
                "Saving engagement UUID for DN",
                engagement_uuid=engagement_uuid,
                source_object=first(converted_objects),
                dn=dn,
            )

        try:
            converted_objects = await self.format_converted_objects(
                converted_objects, json_key
            )
            # In case the engagement exists, but is outdated. If it exists,
            # but is identical, the list will be empty.
            if json_key == "Engagement" and len(converted_objects):
                operation = first(converted_objects)
                engagement, _ = operation
                engagement_uuid = engagement.uuid
                logger.info(
                    "Updating engagement UUID",
                    engagement_uuid=engagement_uuid,
                    source_object=engagement,
                    dn=dn,
                )
        except NoObjectsReturnedException:
            # If any of the objects which this object links to does not exist
            # The dataloader will raise NoObjectsReturnedException
            #
            # This can happen, for example:
            # If converter._import_to_mo_('Address') = True
            # And converter._import_to_mo_('Employee') = False
            #
            # Because an address cannot be imported for an employee that does not
            # exist. The non-existing employee is also not created because
            # converter._import_to_mo_('Employee') = False
            logger.info(
                "Could not format converted objects",
                task="Moving on",
                dn=dn,
            )
            return engagement_uuid

        # TODO: Convert this to an assert? - The above try-catch ensures it is always set, no?
        if not converted_objects:  # pragma: no cover
            logger.info("No converted objects after formatting", dn=dn)
            return engagement_uuid

        # In case the engagement exists, but is outdated.
        # If it exists, but is identical, the list will be empty.
        if json_key == "Engagement":
            # TODO: Why are we extracting the first object as opposed to the last?
            operation = first(converted_objects)
            engagement, _ = operation
            engagement_uuid = engagement.uuid
            logger.info(
                "Updating engagement UUID",
                engagement_uuid=engagement_uuid,
                source_object=engagement,
                dn=dn,
            )

        logger.info(
            "Importing objects",
            converted_objects=converted_objects,
            dn=dn,
        )

        if json_key == "Custom":
            for obj, _ in converted_objects:
                job_list = await obj.sync_to_mo(self.context)
                # TODO: Asyncio.gather?
                for job in job_list:
                    self.uuids_to_ignore.add(job["uuid_to_ignore"])
                    await job["task"]
        else:
            for mo_object, _ in converted_objects:
                self.uuids_to_ignore.add(mo_object.uuid)
            try:
                await self.dataloader.create_or_edit_mo_objects(converted_objects)
            except HTTPStatusError as e:
                # TODO: This could also happen if MO is just busy, right?
                #       In which case we would probably like to retry I imagine?

                # This can happen, for example if a phone number in LDAP is
                # invalid
                logger.warning(
                    "Failed to upload objects",
                    error=e,
                    converted_objects=converted_objects,
                    request=e.request,
                    dn=dn,
                )
                for mo_object, _ in converted_objects:
                    self.uuids_to_ignore.remove(mo_object.uuid)
        return engagement_uuid

    async def refresh_mo_object(self, mo_object_dict: dict[str, Any]) -> None:
        routing_key = mo_object_dict["object_type"]
        payload = mo_object_dict["payload"]

        logger.info(
            "Publishing",
            routing_key=routing_key,
            payload=payload,
        )
        match routing_key:
            case "engagement":
                await self.refresh_engagement(payload)
            case "address":
                await self.refresh_address(payload)
            case "ituser":
                await self.refresh_ituser(payload)
            case _:  # pragma: no cover
                raise NotImplementedError(
                    f"Refreshing {routing_key} is not implemented!"
                )

    async def refresh_object(self, uuid: UUID, object_type: str) -> None:
        """
        Sends out an AMQP message on the internal AMQP system to refresh an object
        """
        mo_object_dict = await self.dataloader.load_mo_object(str(uuid), object_type)
        if mo_object_dict is None:
            raise ValueError(f"Unable to look up {object_type} with UUID: {uuid}")
        await self.refresh_mo_object(mo_object_dict)

    async def refresh_engagement(self, uuid: UUID) -> None:
        await self.dataloader.graphql_client.engagement_refresh(
            self.amqpsystem.exchange_name, uuid
        )

    async def refresh_address(self, uuid: UUID) -> None:
        await self.dataloader.graphql_client.address_refresh(
            self.amqpsystem.exchange_name, uuid
        )

    async def refresh_ituser(self, uuid: UUID) -> None:
        await self.dataloader.graphql_client.ituser_refresh(
            self.amqpsystem.exchange_name, uuid
        )

    async def export_org_unit_addresses_on_engagement_change(
        self, routing_key: MORoutingKey, object_uuid: UUID
    ) -> None:
        # NOTE: This entire function could just be a single call to `address_refresh`
        #       with address_types uuids and org_unit uuids as a filter.
        # TODO: This will need MO to be able to filter org-units by engagement UUIDs
        object_type = get_object_type_from_routing_key(routing_key)
        assert object_type == "engagement"

        response = await self.dataloader.graphql_client.read_engagement_org_unit_uuid(
            object_uuid
        )
        org_unit_uuids = [
            result.current.org_unit_uuid
            for result in response.objects
            if result.current
        ]
        org_unit_uuid = one(org_unit_uuids)

        # Load UUIDs for all addresses in this org-unit
        org_unit_address_uuids = []
        for address_type_uuid in self.converter.org_unit_address_type_info.keys():
            # TODO: We should be able to bulk this as one query
            # NOTE: This function actually loads the address UUIDs, then the objects
            #       just so we can extract the UUIDs from the objects.
            org_unit_addresses = await self.dataloader.load_mo_org_unit_addresses(
                org_unit_uuid,
                address_type_uuid,
            )
            org_unit_address_uuids.extend(
                [address.uuid for address in org_unit_addresses]
            )

        # Export this org-unit's addresses to LDAP by publishing to internal AMQP
        await asyncio.gather(
            *[
                self.refresh_address(org_unit_address_uuid)
                for org_unit_address_uuid in org_unit_address_uuids
            ]
        )

    async def refresh_employee(self, employee_uuid: UUID):
        """
        Sends out AMQP-messages for all objects related to an employee
        """
        # NOTE: Should this not refresh the employee itself as well?
        logger.info("Refreshing employee", uuid=str(employee_uuid))

        # Load address types and it-user types
        address_type_uuids = parse_obj_as(
            list[UUID], list(self.converter.employee_address_type_info.keys())
        )
        it_system_uuids = parse_obj_as(
            list[UUID], list(self.converter.it_system_info.keys())
        )

        refresh_addresses = self.dataloader.graphql_client.person_address_refresh(
            self.amqpsystem.exchange_name, employee_uuid, address_type_uuids
        )
        refresh_engagements = self.dataloader.graphql_client.person_engagement_refresh(
            self.amqpsystem.exchange_name, employee_uuid
        )
        refresh_itusers = self.dataloader.graphql_client.person_ituser_refresh(
            self.amqpsystem.exchange_name, employee_uuid, it_system_uuids
        )

        await asyncio.gather(*[refresh_addresses, refresh_engagements, refresh_itusers])
