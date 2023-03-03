# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
"""
Created on Fri Mar  3 09:46:15 2023

@author: nick
"""
import datetime
from typing import Any
from uuid import UUID
from uuid import uuid4

import structlog
from fastramqpi.context import Context
from ramqp.mo.models import MORoutingKey
from ramqp.mo.models import ObjectType
from ramqp.mo.models import PayloadType

from .exceptions import MultipleObjectsReturnedException
from .exceptions import NotSupportedException
from .ldap import cleanup

# UUIDs in this list will be ignored by listen_to_changes ONCE
uuids_to_ignore: dict[UUID, list[datetime.datetime]] = {}
logger = structlog.get_logger()


async def listen_to_changes_in_employees(
    context: Context,
    payload: PayloadType,
    routing_key: MORoutingKey,
    delete: bool,
    current_objects_only: bool,
) -> None:

    logger.info("[MO] Registered change in the employee model")
    user_context = context["user_context"]
    dataloader = user_context["dataloader"]
    converter = user_context["converter"]
    global uuids_to_ignore

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
    # Note that this is not necessary in listen_to_changes_in_org_units. Because those
    # changes potentially map to multiple employees
    if payload.object_uuid in uuids_to_ignore and uuids_to_ignore[payload.object_uuid]:
        logger.info(f"[listen_to_changes] Ignoring {routing_key}-{payload.object_uuid}")

        # Remove timestamp so it does not get ignored twice.
        oldest_timestamp = min(uuids_to_ignore[payload.object_uuid])
        uuids_to_ignore[payload.object_uuid].remove(oldest_timestamp)
        return None

    # Get MO employee
    changed_employee = await dataloader.load_mo_employee(
        payload.uuid,
        current_objects_only=current_objects_only,
    )
    logger.info(f"Found Employee in MO: {changed_employee}")

    mo_object_dict: dict[str, Any] = {"mo_employee": changed_employee}

    if routing_key.object_type == ObjectType.EMPLOYEE:
        logger.info("[MO] Change registered in the employee object type")

        # Convert to LDAP
        ldap_employee = converter.to_ldap(mo_object_dict, "Employee")

        # Upload to LDAP - overwrite because all employee fields are unique.
        # One person cannot have multiple names.
        await dataloader.modify_ldap_object(
            ldap_employee,
            "Employee",
            overwrite=True,
            delete=delete,
        )

    elif routing_key.object_type == ObjectType.ADDRESS:
        logger.info("[MO] Change registered in the address object type")

        # Get MO address
        changed_address = await dataloader.load_mo_address(
            payload.object_uuid,
            current_objects_only=current_objects_only,
        )
        address_type_uuid = str(changed_address.address_type.uuid)
        json_key = converter.get_address_type_user_key(address_type_uuid)

        logger.info(f"Obtained address type user key = {json_key}")
        mo_object_dict["mo_employee_address"] = changed_address

        # Convert & Upload to LDAP
        await dataloader.modify_ldap_object(
            converter.to_ldap(mo_object_dict, json_key),
            json_key,
            delete=delete,
        )

        addresses_in_mo = await dataloader.load_mo_employee_addresses(
            changed_employee.uuid, changed_address.address_type.uuid
        )

        await cleanup(
            json_key,
            "value",
            "mo_employee_address",
            addresses_in_mo,
            user_context,
            changed_employee,
        )

    elif routing_key.object_type == ObjectType.IT:
        logger.info("[MO] Change registered in the IT object type")

        # Get MO IT-user
        changed_it_user = await dataloader.load_mo_it_user(
            payload.object_uuid,
            current_objects_only=current_objects_only,
        )
        it_system_type_uuid = changed_it_user.itsystem.uuid
        json_key = converter.get_it_system_user_key(it_system_type_uuid)

        logger.info(f"Obtained IT system name = {json_key}")
        mo_object_dict["mo_employee_it_user"] = changed_it_user

        # Convert & Upload to LDAP
        await dataloader.modify_ldap_object(
            converter.to_ldap(mo_object_dict, json_key),
            json_key,
            delete=delete,
        )

        # Load IT users belonging to this employee
        it_users_in_mo = await dataloader.load_mo_employee_it_users(
            changed_employee.uuid, it_system_type_uuid
        )

        await cleanup(
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
        changed_engagement = await dataloader.load_mo_engagement(
            payload.object_uuid,
            current_objects_only=current_objects_only,
        )

        json_key = "Engagement"
        mo_object_dict["mo_employee_engagement"] = changed_engagement

        # Convert & Upload to LDAP
        # Note: We upload an engagement to LDAP regardless of its 'primary' attribute.
        # Because it looks like you cannot set 'primary' when creating an engagement
        # in the OS2mo GUI.
        await dataloader.modify_ldap_object(
            converter.to_ldap(mo_object_dict, json_key),
            json_key,
            delete=delete,
        )

        engagements_in_mo = await dataloader.load_mo_employee_engagements(
            changed_employee.uuid
        )

        await cleanup(
            json_key,
            "user_key",
            "mo_employee_engagement",
            engagements_in_mo,
            user_context,
            changed_employee,
        )


async def listen_to_changes_in_org_units(
    context: Context,
    payload: PayloadType,
    routing_key: MORoutingKey,
    delete: bool,
    current_objects_only: bool,
) -> None:

    user_context = context["user_context"]
    dataloader = user_context["dataloader"]
    converter = user_context["converter"]

    # When an org-unit is changed we need to update the org unit info. So we
    # know the new name of the org unit in case it was changed
    if routing_key.object_type == ObjectType.ORG_UNIT:
        logger.info("Updating org unit info")
        converter.org_unit_info = dataloader.load_mo_org_units()
        converter.check_org_unit_info_dict()

    if routing_key.object_type == ObjectType.ADDRESS:
        logger.info("[MO] Change registered in the address object type")

        # Get MO address
        changed_address = await dataloader.load_mo_address(
            payload.object_uuid,
            current_objects_only=current_objects_only,
        )
        address_type_uuid = str(changed_address.address_type.uuid)
        json_key = converter.address_type_info[address_type_uuid]["user_key"]

        logger.info(f"Obtained address type user key = {json_key}")

        ldap_object_class = converter.find_ldap_object_class(json_key)
        employee_object_class = converter.find_ldap_object_class("Employee")

        if ldap_object_class != employee_object_class:
            raise NotSupportedException(
                (
                    "Mapping organization unit addresses "
                    "to non-employee objects is not supported"
                )
            )

        affected_employees = await dataloader.load_mo_employees_in_org_unit(
            payload.uuid
        )
        logger.info(f"[MO] Found {len(affected_employees)} affected employees")

        for affected_employee in affected_employees:
            mo_object_dict = {
                "mo_employee": affected_employee,
                "mo_org_unit_address": changed_address,
            }

            # Convert & Upload to LDAP
            await dataloader.modify_ldap_object(
                converter.to_ldap(mo_object_dict, json_key),
                json_key,
                delete=delete,
            )

            addresses_in_mo = await dataloader.load_mo_org_unit_addresses(
                payload.uuid, changed_address.address_type.uuid
            )

            await cleanup(
                json_key,
                "value",
                "mo_org_unit_address",
                addresses_in_mo,
                user_context,
                affected_employee,
            )


async def format_converted_objects(converted_objects, json_key, user_context):
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
        if converted_objects[0].person:
            objects_in_mo = await dataloader.load_mo_employee_addresses(
                converted_objects[0].person.uuid, converted_objects[0].address_type.uuid
            )
        elif converted_objects[0].org_unit:
            objects_in_mo = await dataloader.load_mo_org_unit_addresses(
                converted_objects[0].org_unit.uuid,
                converted_objects[0].address_type.uuid,
            )
        else:
            logger.info(
                (
                    "Could not format converted objects: "
                    "An address needs to have either a person uuid OR an org unit uuid"
                )
            )
            return []
        value_key = "value"

    # Load engagements already in MO
    elif mo_object_class == "Engagement":
        objects_in_mo = await dataloader.load_mo_employee_engagements(
            converted_objects[0].person.uuid
        )
        value_key = "user_key"
        user_keys = [o.user_key for o in objects_in_mo]

        # If we have duplicate user_keys, remove those which are the same as the primary
        # engagement's user_key
        if len(set(user_keys)) < len(user_keys):
            primary = [await dataloader.is_primary(o.uuid) for o in objects_in_mo]

            # There can be only one primary unit. Not sure what to do if there are
            # multiple, so better just do nothing.
            if sum(primary) == 1:
                primary_engagement = objects_in_mo[primary.index(True)]
                logger.info(
                    (
                        f"Found primary engagement with "
                        f"uuid={primary_engagement.uuid},"
                        f"user_key='{primary_engagement.user_key}'"
                    )
                )
                logger.info("Removing engagements with identical user keys")
                objects_in_mo = [
                    o
                    for o in objects_in_mo
                    if o == primary_engagement
                    or o.user_key != primary_engagement.user_key
                ]

    elif mo_object_class == "ITUser":
        # If an ITUser already exists, MO throws an error - it cannot be updated if the
        # key is identical to an existing key.
        it_users_in_mo = await dataloader.load_mo_employee_it_users(
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
            converted_object_uuid_checked = mo_class(**mo_object_dict_to_upload)

            # If an object is identical to the one already there, it does not need
            # to be uploaded.
            if converted_object_uuid_checked == matching_object:
                logger.info(
                    "Converted object is identical to existing object. Skipping."
                )
            else:
                converted_objects_uuid_checked.append(converted_object_uuid_checked)

        elif values_in_mo.count(converted_object_value) == 0:
            converted_objects_uuid_checked.append(converted_object)
        else:
            logger.warning(
                f"Could not determine which '{json_key}' MO object "
                f"{value_key}='{converted_object_value}' belongs to. Skipping"
            )

    return converted_objects_uuid_checked


async def import_single_user(cpr: str, context: Context):
    global uuids_to_ignore
    # Get the employee's uuid (if he exists)
    # Note: We could optimize this by loading all relevant employees once. But:
    # - What if an employee is created by someone else while this code is running?
    # - We don't need the additional speed. This is meant as a one-time import
    # - We won't gain much; This is an asynchronous request. The code moves on while
    #   we are waiting for MO's response
    user_context = context["user_context"]
    converter = user_context["converter"]
    dataloader = user_context["dataloader"]

    detected_json_keys = converter.get_ldap_to_mo_json_keys()

    employee_uuid = await dataloader.find_mo_employee_uuid(cpr)
    if not employee_uuid:
        employee_uuid = uuid4()

    # First import the Employee
    # Then import other objects (which link to the employee)
    json_keys = ["Employee"] + [k for k in detected_json_keys if k != "Employee"]

    for json_key in json_keys:
        if not converter.__import_to_mo__(json_key):
            logger.info(f"__import_to_mo__ == False for json_key = '{json_key}'")
            continue
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
            converted_objects, json_key, user_context
        )

        if len(converted_objects) > 0:
            logger.info(f"Importing {converted_objects}")

            for mo_object in converted_objects:
                if mo_object.uuid in uuids_to_ignore:
                    uuids_to_ignore[mo_object.uuid].append(datetime.datetime.now())
                else:
                    uuids_to_ignore[mo_object.uuid] = [datetime.datetime.now()]
            await dataloader.upload_mo_objects(converted_objects)
