# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
"""
Created on Fri Mar  3 09:46:15 2023

@author: nick
"""
import datetime
from typing import Any
from typing import Union
from uuid import UUID
from uuid import uuid4

import structlog
from fastramqpi.context import Context
from ramqp.mo.models import MORoutingKey
from ramqp.mo.models import ObjectType
from ramqp.mo.models import PayloadType

from .exceptions import IgnoreChanges
from .exceptions import MultipleObjectsReturnedException
from .exceptions import NotSupportedException
from .ldap import cleanup


class IgnoreMe:
    def __init__(self):
        self.ignore_dict: dict[str, list[datetime.datetime]] = {}
        self.logger = structlog.get_logger()

    def __getitem__(self, key):
        return self.ignore_dict[str(key)]

    def __len__(self):
        return len(self.ignore_dict)

    def clean(self):
        # Remove all timestamps which have been in ignore_dict for more than x seconds.
        now = datetime.datetime.now()
        for str_to_ignore, timestamps in self.ignore_dict.items():
            for timestamp in timestamps:
                age_in_seconds = (now - timestamp).total_seconds()
                if age_in_seconds > 60:
                    self.logger.info(
                        (
                            f"Removing timestamp belonging to {str_to_ignore} "
                            "from ignore_dict. "
                            f"It is {age_in_seconds} seconds old"
                        )
                    )
                    timestamps.remove(timestamp)

    def add(self, str_to_add: Union[str, UUID]):
        if type(str_to_add) is not str:
            str_to_add = str(str_to_add)
        if str_to_add in self.ignore_dict:
            self.ignore_dict[str(str_to_add)].append(datetime.datetime.now())
        else:
            self.ignore_dict[str(str_to_add)] = [datetime.datetime.now()]

    def check(self, str_to_check: Union[str, UUID]):
        if type(str_to_check) is not str:
            str_to_check = str(str_to_check)
        self.clean()

        if str_to_check in self.ignore_dict and self.ignore_dict[str_to_check]:

            # Remove timestamp so it does not get ignored twice.
            oldest_timestamp = min(self.ignore_dict[str_to_check])
            self.ignore_dict[str_to_check].remove(oldest_timestamp)
            raise IgnoreChanges(f"[check_ignore_dict] Ignoring {str_to_check}")


class SyncTool:
    def __init__(self, context: Context):

        # UUIDs in this list will be ignored by listen_to_changes ONCE
        # self.uuids_to_ignore = self.initialize_ignore_dict()
        self.uuids_to_ignore = IgnoreMe()

        self.logger = structlog.get_logger()
        self.context = context
        self.user_context = self.context["user_context"]
        self.dataloader = self.user_context["dataloader"]
        self.converter = self.user_context["converter"]

    async def listen_to_changes_in_employees(
        self,
        payload: PayloadType,
        routing_key: MORoutingKey,
        delete: bool,
        current_objects_only: bool,
    ) -> None:

        self.logger.info("[MO] Registered change in the employee model")

        # If the object was uploaded by us, it does not need to be synchronized.
        # Note that this is not necessary in listen_to_changes_in_org_units. Because
        # those changes potentially map to multiple employees
        self.uuids_to_ignore.check(payload.object_uuid)

        # Get MO employee
        changed_employee = await self.dataloader.load_mo_employee(
            payload.uuid,
            current_objects_only=current_objects_only,
        )
        self.logger.info(f"Found Employee in MO: {changed_employee}")

        mo_object_dict: dict[str, Any] = {"mo_employee": changed_employee}

        if routing_key.object_type == ObjectType.EMPLOYEE:
            self.logger.info("[MO] Change registered in the employee object type")

            # Convert to LDAP
            ldap_employee = self.converter.to_ldap(mo_object_dict, "Employee")

            # Upload to LDAP - overwrite because all employee fields are unique.
            # One person cannot have multiple names.
            await self.dataloader.modify_ldap_object(
                ldap_employee,
                "Employee",
                overwrite=True,
                delete=delete,
            )

        elif routing_key.object_type == ObjectType.ADDRESS:
            self.logger.info("[MO] Change registered in the address object type")

            # Get MO address
            changed_address = await self.dataloader.load_mo_address(
                payload.object_uuid,
                current_objects_only=current_objects_only,
            )
            address_type_uuid = str(changed_address.address_type.uuid)
            json_key = self.converter.get_address_type_user_key(address_type_uuid)

            self.logger.info(f"Obtained address type user key = {json_key}")
            mo_object_dict["mo_employee_address"] = changed_address

            # Convert & Upload to LDAP
            await self.dataloader.modify_ldap_object(
                self.converter.to_ldap(mo_object_dict, json_key),
                json_key,
                delete=delete,
            )

            addresses_in_mo = await self.dataloader.load_mo_employee_addresses(
                changed_employee.uuid, changed_address.address_type.uuid
            )

            await cleanup(
                json_key,
                "value",
                "mo_employee_address",
                addresses_in_mo,
                self.user_context,
                changed_employee,
            )

        elif routing_key.object_type == ObjectType.IT:
            self.logger.info("[MO] Change registered in the IT object type")

            # Get MO IT-user
            changed_it_user = await self.dataloader.load_mo_it_user(
                payload.object_uuid,
                current_objects_only=current_objects_only,
            )
            it_system_type_uuid = changed_it_user.itsystem.uuid
            json_key = self.converter.get_it_system_user_key(it_system_type_uuid)

            self.logger.info(f"Obtained IT system name = {json_key}")
            mo_object_dict["mo_employee_it_user"] = changed_it_user

            # Convert & Upload to LDAP
            await self.dataloader.modify_ldap_object(
                self.converter.to_ldap(mo_object_dict, json_key),
                json_key,
                delete=delete,
            )

            # Load IT users belonging to this employee
            it_users_in_mo = await self.dataloader.load_mo_employee_it_users(
                changed_employee.uuid, it_system_type_uuid
            )

            await cleanup(
                json_key,
                "user_key",
                "mo_employee_it_user",
                it_users_in_mo,
                self.user_context,
                changed_employee,
            )

        elif routing_key.object_type == ObjectType.ENGAGEMENT:
            self.logger.info("[MO] Change registered in the Engagement object type")

            # Get MO Engagement
            changed_engagement = await self.dataloader.load_mo_engagement(
                payload.object_uuid,
                current_objects_only=current_objects_only,
            )

            json_key = "Engagement"
            mo_object_dict["mo_employee_engagement"] = changed_engagement

            # Convert & Upload to LDAP
            # We upload an engagement to LDAP regardless of its 'primary' attribute.
            # Because it looks like you cannot set 'primary' when creating an engagement
            # in the OS2mo GUI.
            await self.dataloader.modify_ldap_object(
                self.converter.to_ldap(mo_object_dict, json_key),
                json_key,
                delete=delete,
            )

            engagements_in_mo = await self.dataloader.load_mo_employee_engagements(
                changed_employee.uuid
            )

            await cleanup(
                json_key,
                "user_key",
                "mo_employee_engagement",
                engagements_in_mo,
                self.user_context,
                changed_employee,
            )

    async def listen_to_changes_in_org_units(
        self,
        payload: PayloadType,
        routing_key: MORoutingKey,
        delete: bool,
        current_objects_only: bool,
    ) -> None:

        # When an org-unit is changed we need to update the org unit info. So we
        # know the new name of the org unit in case it was changed
        if routing_key.object_type == ObjectType.ORG_UNIT:
            self.logger.info("Updating org unit info")
            self.converter.org_unit_info = self.dataloader.load_mo_org_units()
            self.converter.check_org_unit_info_dict()

        if routing_key.object_type == ObjectType.ADDRESS:
            self.logger.info("[MO] Change registered in the address object type")

            # Get MO address
            changed_address = await self.dataloader.load_mo_address(
                payload.object_uuid,
                current_objects_only=current_objects_only,
            )
            address_type_uuid = str(changed_address.address_type.uuid)
            json_key = self.converter.address_type_info[address_type_uuid]["user_key"]

            self.logger.info(f"Obtained address type user key = {json_key}")

            ldap_object_class = self.converter.find_ldap_object_class(json_key)
            employee_object_class = self.converter.find_ldap_object_class("Employee")

            if ldap_object_class != employee_object_class:
                raise NotSupportedException(
                    (
                        "Mapping organization unit addresses "
                        "to non-employee objects is not supported"
                    )
                )

            affected_employees = await self.dataloader.load_mo_employees_in_org_unit(
                payload.uuid
            )
            self.logger.info(f"[MO] Found {len(affected_employees)} affected employees")

            for affected_employee in affected_employees:
                mo_object_dict = {
                    "mo_employee": affected_employee,
                    "mo_org_unit_address": changed_address,
                }

                # Convert & Upload to LDAP
                await self.dataloader.modify_ldap_object(
                    self.converter.to_ldap(mo_object_dict, json_key),
                    json_key,
                    delete=delete,
                )

                addresses_in_mo = await self.dataloader.load_mo_org_unit_addresses(
                    payload.uuid, changed_address.address_type.uuid
                )

                await cleanup(
                    json_key,
                    "value",
                    "mo_org_unit_address",
                    addresses_in_mo,
                    self.user_context,
                    affected_employee,
                )

    async def format_converted_objects(self, converted_objects, json_key):
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

        # Load addresses already in MO
        if mo_object_class == "Address":
            if converted_objects[0].person:
                objects_in_mo = await self.dataloader.load_mo_employee_addresses(
                    converted_objects[0].person.uuid,
                    converted_objects[0].address_type.uuid,
                )
            elif converted_objects[0].org_unit:
                objects_in_mo = await self.dataloader.load_mo_org_unit_addresses(
                    converted_objects[0].org_unit.uuid,
                    converted_objects[0].address_type.uuid,
                )
            else:
                self.logger.info(
                    (
                        "Could not format converted objects: "
                        "An address needs to have either a person uuid "
                        "OR an org unit uuid"
                    )
                )
                return []
            value_key = "value"

        # Load engagements already in MO
        elif mo_object_class == "Engagement":
            objects_in_mo = await self.dataloader.load_mo_employee_engagements(
                converted_objects[0].person.uuid
            )
            value_key = "user_key"
            user_keys = [o.user_key for o in objects_in_mo]

            # If we have duplicate user_keys, remove those which are the same as the
            # primary engagement's user_key
            if len(set(user_keys)) < len(user_keys):
                primary = [
                    await self.dataloader.is_primary(o.uuid) for o in objects_in_mo
                ]

                # There can be only one primary unit. Not sure what to do if there are
                # multiple, so better just do nothing.
                if sum(primary) == 1:
                    primary_engagement = objects_in_mo[primary.index(True)]
                    self.logger.info(
                        (
                            f"Found primary engagement with "
                            f"uuid={primary_engagement.uuid},"
                            f"user_key='{primary_engagement.user_key}'"
                        )
                    )
                    self.logger.info("Removing engagements with identical user keys")
                    objects_in_mo = [
                        o
                        for o in objects_in_mo
                        if o == primary_engagement
                        or o.user_key != primary_engagement.user_key
                    ]

        elif mo_object_class == "ITUser":
            # If an ITUser already exists, MO throws an error - it cannot be updated if
            # the key is identical to an existing key.
            it_users_in_mo = await self.dataloader.load_mo_employee_it_users(
                converted_objects[0].person.uuid, converted_objects[0].itsystem.uuid
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
        mo_attributes = self.converter.get_mo_attributes(json_key)

        # Set uuid if a matching one is found. so an object gets updated
        # instead of duplicated
        converted_objects_uuid_checked = []
        for converted_object in converted_objects:
            values_in_mo = [getattr(a, value_key) for a in objects_in_mo_dict.values()]
            converted_object_value = getattr(converted_object, value_key)

            if values_in_mo.count(converted_object_value) == 1:
                self.logger.info(
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
                        self.logger.info(
                            f"Setting {key} = {converted_mo_object_dict[key]}"
                        )
                        mo_object_dict_to_upload[key] = converted_mo_object_dict[key]

                mo_class = self.converter.import_mo_object_class(json_key)
                converted_object_uuid_checked = mo_class(**mo_object_dict_to_upload)

                # If an object is identical to the one already there, it does not need
                # to be uploaded.
                if converted_object_uuid_checked == matching_object:
                    self.logger.info(
                        "Converted object is identical to existing object. Skipping."
                    )
                else:
                    converted_objects_uuid_checked.append(converted_object_uuid_checked)

            elif values_in_mo.count(converted_object_value) == 0:
                converted_objects_uuid_checked.append(converted_object)
            else:
                self.logger.warning(
                    f"Could not determine which '{json_key}' MO object "
                    f"{value_key}='{converted_object_value}' belongs to. Skipping"
                )

        return converted_objects_uuid_checked

    async def import_single_user(self, cpr: str, context: Context):
        # Get the employee's uuid (if he exists)
        # Note: We could optimize this by loading all relevant employees once. But:
        # - What if an employee is created by someone else while this code is running?
        # - We don't need the additional speed. This is meant as a one-time import
        # - We won't gain much; This is an asynchronous request. The code moves on while
        #   we are waiting for MO's response
        detected_json_keys = self.converter.get_ldap_to_mo_json_keys()

        employee_uuid = await self.dataloader.find_mo_employee_uuid(cpr)
        if not employee_uuid:
            employee_uuid = uuid4()

        # First import the Employee
        # Then import other objects (which link to the employee)
        json_keys = ["Employee"] + [k for k in detected_json_keys if k != "Employee"]

        for json_key in json_keys:
            if not self.converter.__import_to_mo__(json_key):
                self.logger.info(
                    f"__import_to_mo__ == False for json_key = '{json_key}'"
                )
                continue
            self.logger.info(f"Loading {json_key} object")
            try:
                loaded_object = self.dataloader.load_ldap_cpr_object(cpr, json_key)
            except MultipleObjectsReturnedException as e:
                self.logger.warning(f"Could not upload {json_key} object: {e}")
                break

            self.logger.info(f"Loaded {loaded_object.dn}")

            converted_objects = self.converter.from_ldap(
                loaded_object, json_key, employee_uuid=employee_uuid
            )

            if len(converted_objects) == 0:
                self.logger.info("No converted objects")
                continue

            converted_objects = await self.format_converted_objects(
                converted_objects, json_key
            )

            if len(converted_objects) > 0:
                self.logger.info(f"Importing {converted_objects}")

                for mo_object in converted_objects:
                    self.uuids_to_ignore.add(mo_object.uuid)

                await self.dataloader.upload_mo_objects(converted_objects)