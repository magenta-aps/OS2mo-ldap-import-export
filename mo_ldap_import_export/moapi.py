# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
from datetime import UTC
from datetime import datetime
from typing import Protocol
from typing import TypeVar
from uuid import UUID

import structlog
from fastapi.encoders import jsonable_encoder
from more_itertools import one
from more_itertools import only
from ramodels.mo.details.it_system import ITUser
from ramodels.mo.employee import Employee

from .autogenerated_graphql_client import GraphQLClient
from .autogenerated_graphql_client.base_model import UNSET
from .config import Settings
from .exceptions import MultipleObjectsReturnedException
from .exceptions import UUIDNotFoundException

logger = structlog.stdlib.get_logger()


class Validity(Protocol):
    @property
    def from_(self) -> datetime | None:  # pragma: no cover
        ...

    @property
    def to(self) -> datetime | None:  # pragma: no cover
        ...


class ValidityModel(Protocol):
    @property
    def validity(self) -> Validity:  # pragma: no cover
        ...


T = TypeVar("T", bound=ValidityModel)


def extract_current_or_latest_validity(validities: list[T]) -> T | None:
    """
    Check each validity in a list of validities and return the one which is either
    valid today, or has the latest end-date
    """
    if len(validities) <= 1:
        return only(validities)

    def is_current(val: T) -> bool:
        # Cannot use datetime.utcnow as it is not timezone aware
        now_utc = datetime.now(UTC)

        match (val.validity.from_, val.validity.to):
            case (None, None):
                return True
            case (start, None):
                assert start is not None
                return start < now_utc
            case (None, end):
                assert end is not None
                return now_utc < end
            case (start, end):
                assert start is not None
                assert end is not None
                return start < now_utc < end
            case _:  # pragma: no cover
                raise AssertionError()

    # If any of the validities is valid today, return it
    current_validity = only(filter(is_current, validities))
    if current_validity:
        return current_validity
    # Otherwise return the latest
    # TODO: Does this actually make sense? - Should we not return the one which is the
    #       closest to now, rather than the one that is the furthest into the future?
    # Cannot use datetime.max directly as it is not timezone aware
    datetime_max_utc = datetime.max.replace(tzinfo=UTC)
    latest_validity = max(
        validities, key=lambda val: val.validity.to or datetime_max_utc
    )
    return latest_validity


class MOAPI:
    def __init__(self, settings: Settings, graphql_client: GraphQLClient) -> None:
        self.settings = settings
        self.graphql_client = graphql_client

    async def find_mo_employee_uuid_via_ituser(self, unique_uuid: UUID) -> set[UUID]:
        result = await self.graphql_client.read_employee_uuid_by_ituser_user_key(
            str(unique_uuid)
        )
        return {
            ituser.current.employee_uuid
            for ituser in result.objects
            if ituser.current is not None and ituser.current.employee_uuid is not None
        }

    async def get_it_system_uuid(self, itsystem_user_key: str) -> str:
        result = await self.graphql_client.read_itsystem_uuid(itsystem_user_key)
        exception = UUIDNotFoundException(
            f"itsystem not found, user_key: {itsystem_user_key}"
        )
        return str(one(result.objects, too_short=exception).uuid)

    async def load_mo_employee(
        self, uuid: UUID, current_objects_only=True
    ) -> Employee | None:
        start = end = UNSET if current_objects_only else None
        results = await self.graphql_client.read_employees([uuid], start, end)
        result = only(results.objects)
        if result is None:
            return None
        result_entry = extract_current_or_latest_validity(result.validities)
        if result_entry is None:
            return None
        entry = jsonable_encoder(result_entry)
        entry.pop("validity")
        return Employee(**entry)

    async def get_ldap_it_system_uuid(self) -> str | None:
        """
        Return the IT system uuid belonging to the LDAP-it-system
        Return None if the LDAP-it-system is not found.
        """
        if self.settings.ldap_it_system is None:
            return None

        try:
            return await self.get_it_system_uuid(self.settings.ldap_it_system)
        except UUIDNotFoundException:
            logger.info(
                "UUID Not found",
                suggestion=f"Does the '{self.settings.ldap_it_system}' it-system exist?",
            )
            return None

    async def load_mo_class_uuid(self, user_key: str) -> UUID | None:
        """Find the UUID of a class by user-key.

        Args:
            user_key: The user-key to lookup.

        Raises:
            MultipleObjectsReturnedException:
                If multiple classes share the same user-key.

        Returns:
            The UUID of the class or None if not found.
        """
        result = await self.graphql_client.read_class_uuid(user_key)
        too_long = MultipleObjectsReturnedException(
            f"Found multiple classes with user_key = '{user_key}': {result}"
        )
        klass = only(result.objects, too_long=too_long)
        if klass is None:
            return None
        return klass.uuid

    async def load_mo_facet_uuid(self, user_key: str) -> UUID | None:
        """Find the UUID of a facet by user-key.

        Args:
            user_key: The user-key to lookup.

        Raises:
            MultipleObjectsReturnedException:
                If multiple facets share the same user-key.

        Returns:
            The uuid of the facet or None if not found.
        """
        result = await self.graphql_client.read_facet_uuid(user_key)
        too_long = MultipleObjectsReturnedException(
            f"Found multiple facets with user_key = '{user_key}': {result}"
        )
        facet = only(result.objects, too_long=too_long)
        if facet is None:
            return None
        return facet.uuid

    async def load_mo_it_user(
        self, uuid: UUID, current_objects_only=True
    ) -> ITUser | None:
        start = end = UNSET if current_objects_only else None
        results = await self.graphql_client.read_itusers([uuid], start, end)
        result = only(results.objects)
        if result is None:
            return None
        result_entry = extract_current_or_latest_validity(result.validities)
        if result_entry is None:
            return None
        entry = jsonable_encoder(result_entry)
        return ITUser.from_simplified_fields(
            user_key=entry["user_key"],
            itsystem_uuid=entry["itsystem_uuid"],
            from_date=entry["validity"]["from"],
            uuid=uuid,
            to_date=entry["validity"]["to"],
            person_uuid=entry["employee_uuid"],
            engagement_uuid=entry["engagement_uuid"],
        )
