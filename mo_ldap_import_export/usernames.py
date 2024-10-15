# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
import re
from collections.abc import Iterator
from typing import cast
from uuid import UUID

import structlog
from fastramqpi.context import Context
from ldap3 import Connection
from more_itertools import one
from more_itertools import split_when
from ramodels.mo.employee import Employee

from .config import Settings
from .config import UsernameGeneratorConfig
from .dataloaders import DataLoader
from .ldap import paged_search
from .utils import combine_dn_strings
from .utils import remove_vowels

logger = structlog.stdlib.get_logger()


class UserNameGenerator:
    """
    Class with functions to generate valid LDAP usernames.

    Each customer could have his own username generator function in here. All you need
    to do, is refer to the proper function inside the json dict.
    """

    def __init__(
        self,
        context: Context,
        settings: Settings,
        username_generator_config: UsernameGeneratorConfig,
        dataloader: DataLoader,
        ldap_connection: Connection,
    ) -> None:
        # Reference needed for deferred lookup of converter in context
        self.user_context = context["user_context"]

        self.settings = settings
        # TODO: Eliminate dataloader dependency
        self.dataloader = dataloader
        self.ldap_connection = ldap_connection

        self.char_replacement = username_generator_config.char_replacement
        self.forbidden_usernames = username_generator_config.forbidden_usernames
        self.combinations = username_generator_config.combinations_to_try
        logger.info("Found forbidden usernames", count=len(self.forbidden_usernames))

    @property
    def converter(self):
        from .converters import LdapConverter

        return cast(LdapConverter, self.user_context["converter"])

    async def get_existing_values(self, attributes: list[str]):
        searchParameters = {
            "search_filter": "(objectclass=*)",
            "attributes": attributes,
        }
        search_base = self.settings.ldap_search_base
        search_result = await paged_search(
            self.settings,
            self.ldap_connection,
            searchParameters,
            search_base,
        )

        output = {}
        for attribute in attributes:
            values = []
            for entry in search_result:
                value = entry["attributes"][attribute]
                if not value:
                    continue
                if isinstance(value, list):
                    value = one(value)
                values.append(value.lower())
            output[attribute] = values
        return output

    def _make_cn(self, username_string: str):
        return f"CN={username_string}"

    def _make_dn(self, username_string: str) -> str:
        cn = self._make_cn(username_string)
        dn = combine_dn_strings(
            [
                cn,
                self.settings.ldap_ou_for_new_users,
                self.settings.ldap_search_base,
            ]
        )

        return dn

    def _name_fixer(self, name_parts: list[str]) -> list[str]:
        """Cleanup a structured name to remove non-ascii characters.

        Context:
            self.char_replacement:
                Dictionary from one set of characters to their replacements.

        Args:
            name_parts: An array of names; given_name, middlenames, surname.

        Returns:
            `name_parts` where non-ascii characters have been replaced
            according to the char_replacement map, or if unmatched, removed.
        """

        def fix_name(name: str) -> str:
            # Replace according to replacement list
            for char, replacement in self.char_replacement.items():
                name = name.replace(char, replacement)
            # Remove all remaining characters outside a-z
            return re.sub(r"[^a-z]+", "", name.lower())

        return list(map(fix_name, name_parts))

    def _machine_readable_combi(self, combi: str) -> tuple[list[int | None], int]:
        """Converts a name to a machine processable internal format.

        Args:
            combi: Combination to create a username from. For example "F123LX".

        Returns:
            A two-tuple containing the internal combi format and the max name
            entry we will look up.

        Example:
            Given `combi = "F123LX"`, we return `([0,1,2,3,-1,None], 3)`.
            The name name entry `3` is simply the highest number contained
            within the internal combi format, and the internal combi format
            is produced according to the following lookup table.
        """
        char2pos = {
            # First name
            "F": 0,
            # First middle name
            "1": 1,
            # Second middle name
            "2": 2,
            # Third middle name
            "3": 3,
            # Last name (independent of middle names)
            "L": -1,
            "X": None,
        }
        readable_combi = [char2pos[x] for x in combi]
        max_position = max((x for x in readable_combi if x is not None), default=-1)
        return readable_combi, max_position

    def _create_from_combi(self, name_parts: list[str], combi: str) -> str | None:
        """Create a username from a name and a combination.

        Args:
            name_parts: An array of names; given_name, middlenames, surname.
            combi: Combination to create a username from. For example "F123LX".

        Returns:
            A username generated according to the combination.
            Note that this username may still contain 'X' characters, which need
            to be replaced with a number.
        """
        # Convert combi into machine readable code.
        # For example: combi = "F123LX" returns code = [0,1,2,3,-1,None]
        (code, max_position) = self._machine_readable_combi(combi)

        # Do not use codes that uses more names than the actual person has
        if max_position > len(name_parts) - 2:
            return None

        # Do not use codes that require a last name if the person has no last name
        if not name_parts[-1] and -1 in code:
            return None

        # Split code into groups on changes
        # For example [0, 1, 1, 1, -1] returns [[0], [1,1,1], [-1]]
        splits = split_when(code, lambda x, y: x != y)
        # Transform into code + count
        # For example [[0], [1,1,1], [-1]] returns [(0,1), (1,3), (-1,1)]
        groups = [(x[0], len(x)) for x in splits]

        def code2char(x: int | None, current_char: int) -> str:
            # None translates to 'X'. This is replaced with a number later on.
            if x is None:
                return "X"
            return name_parts[x][current_char].lower()

        username = ""
        # Each group has the same character
        for x, num in groups:
            # Sanity check that the name is long enough
            if x is not None and num > len(name_parts[x]):
                return None
            for current_char in range(num):
                username += code2char(x, current_char)
        return username

    def _create_username(self, name: list[str], existing_usernames: list[str]) -> str:
        """
        Create a new username in accordance with the rules specified in the json file.
        The username will be the highest quality available and the value will be
        added to list of used names, so consequtive calles with the same name
        will keep returning new names until the algorithm runs out of options
        and a RuntimeException is raised.

        :param name: Name of the user given as a list with at least two elements.
        :return: New username generated.

        Inspired by ad_integration/usernames.py
        """

        def permutations(username: str) -> Iterator[str]:
            # The permutation is a number inside the username, it is normally only used in
            # case a username is already occupied. It can be specified using 'X' in the
            # username template.
            #
            # The first attempted permutation should be '2':
            # For example; If 'cvt' is occupied, a username 'cvt2' will be generated.
            #
            # The last attempted permutation is '9' - because we would like to limit the
            # permutation counter to a single digit.
            for permutation_counter in range(2, 10):
                yield username.replace("X", str(permutation_counter))

        def forbidden(username: str) -> bool:
            # Check if core username is legal
            return username.replace("X", "") in self.forbidden_usernames

        def existing(username: str) -> bool:
            return username in existing_usernames

        # Cleanup names
        name = self._name_fixer(name)
        # Generate usernames from names and combinations
        usernames = (
            self._create_from_combi(name, combi) for combi in self.combinations
        )
        for username in usernames:
            if username is None:
                continue
            if forbidden(username):
                continue
            p_usernames = permutations(username)
            for p_username in p_usernames:
                if existing(p_username):
                    continue
                return p_username
        raise RuntimeError("Failed to create user name.")

    def _create_common_name(
        self, name: list[str], existing_common_names: list[str]
    ) -> str:
        """
        Create an LDAP-style common name (CN) based on first and last name

        If a name exists, "_2" is added. If that one also exists, "_3" is added,
        and so on

        Examples
        -------------
        >>> _create_common_name(["Keanu","Reeves"])
        >>> "Keanu Reeves"
        """

        def permutations(username: str) -> Iterator[str]:
            yield username
            for permutation_counter in range(2, 1000):
                yield username + "_" + str(permutation_counter)

        def existing(potential_name: str) -> bool:
            return potential_name.lower() in existing_common_names

        name = [n for n in name if n]
        num_middlenames = len(name) - 2

        # Shorten a name if it is over 64 chars
        # see http://msdn.microsoft.com/en-us/library/ms675449(VS.85).aspx
        common_name = " ".join(name)
        while len(common_name) > 60 and num_middlenames > 0:
            # Remove one middlename
            num_middlenames -= 1
            # Try to make a name with the selected number of middlenames
            givenname, *middlenames, surname = name
            middlenames = middlenames[:num_middlenames]
            common_name = " ".join([givenname] + middlenames + [surname])

        # Cut off the name (leave place for the permutation counter)
        common_name = common_name[:60]

        for potential_name in permutations(common_name):
            if existing(potential_name):
                continue
            return potential_name

        raise RuntimeError("Failed to create common name")

    async def _get_employee_ldap_attributes(self, employee: Employee, dn: str):
        if self.settings.conversion_mapping.mo2ldap:
            return await self.dataloader.sync_tool.render_ldap2mo(employee.uuid, dn)
        else:
            # TODO: Remove this when everyone uses the new template
            employee_ldap = await self.converter.to_ldap(
                {"mo_employee": employee}, "Employee", dn
            )
            attributes = employee_ldap.dict()
            attributes.pop("dn")
            return attributes

    async def _get_existing_names(self):
        match self.settings.ldap_dialect:
            case "Standard":
                login_fields = ["distinguishedName"]
            case "AD":
                login_fields = ["sAMAccountName", "userPrincipalName"]
            case _:  # pragma: no cover
                assert AssertionError("Unknown LDAP dialect")

        # TODO: Consider if it is better to fetch all names or candidate names
        existing_values = await self.get_existing_values(["cn"] + login_fields)

        match self.settings.ldap_dialect:
            case "Standard":
                existing_usernames = existing_values["distinguishedName"]
            case "AD":
                user_principal_names = [
                    s.split("@")[0] for s in existing_values["userPrincipalName"]
                ]
                existing_usernames = (
                    existing_values["sAMAccountName"] + user_principal_names
                )
            case _:  # pragma: no cover
                raise AssertionError("Unknown LDAP dialect")

        existing_common_names = existing_values["cn"]

        return existing_usernames, existing_common_names

    async def generate_dn(self, employee: Employee) -> str:
        """
        Generates a LDAP DN (Distinguished Name) based on information from a MO Employee
        object.

        Also adds an object to LDAP with this DN
        """
        existing_usernames, existing_common_names = await self._get_existing_names()

        givenname = employee.givenname
        surname = employee.surname
        name = givenname.split(" ")[:4] + [surname]

        username = self._create_username(name, existing_usernames)
        logger.info(
            "Generated username based on name",
            givenname=givenname,
            surname=surname,
            username=username,
        )

        common_name = self._create_common_name(name, existing_common_names)
        logger.info(
            "Generated CommonName based on name",
            givenname=givenname,
            surname=surname,
            common_name=common_name,
        )

        dn = self._make_dn(common_name)
        employee_attributes = await self._get_employee_ldap_attributes(employee, dn)
        other_attributes = {}
        if self.settings.ldap_dialect == "AD":
            other_attributes = {"sAMAccountName": username}
        await self.dataloader.ldapapi.add_ldap_object(
            dn, employee_attributes | other_attributes
        )
        return dn


class AlleroedUserNameGenerator(UserNameGenerator):
    def generate_username(self, name, existing_usernames: list[str]):
        # Remove vowels from all but first name
        name = [name[0]] + [remove_vowels(n) for n in self._name_fixer(name)[1:]]

        return self._create_username(name, existing_usernames)

    async def generate_dn(self, employee: Employee) -> str:
        """
        Generates a LDAP DN (Distinguished Name) based on information from a MO Employee
        object.

        Also adds an object to LDAP with this DN

        Follows guidelines from https://redmine.magenta-aps.dk/issues/56080
        """
        assert self.settings.ldap_dialect == "AD"

        existing_usernames, existing_common_names = await self._get_existing_names()

        # "existing_usernames_in_mo" covers all usernames which MO has ever generated.
        # Because we never delete from MO's database; We just put end-dates on objects.
        #
        # We need to block these usernames from being generated, because it is possible
        # That MO generates a user, which is deleted from AD some years later. In that
        # Case we should never generate the username of the deleted user.
        # Ref: https://redmine.magenta-aps.dk/issues/57043
        itsystem_uuid = await self.dataloader.moapi.get_it_system_uuid("ADSAMA")
        result = await self.dataloader.graphql_client.read_all_ituser_user_keys_by_itsystem_uuid(
            UUID(itsystem_uuid)
        )
        # TODO: Keep this as a set and convert all operations to set operations
        existing_usernames_in_mo = list(
            {validity.user_key for obj in result.objects for validity in obj.validities}
        )

        givenname = employee.givenname.strip()
        surname = employee.surname
        name = givenname.split(" ")[:4] + [surname]

        common_name = self._create_common_name(name, existing_common_names)
        logger.info("Generated CommonName for {givenname} {surname}: '{common_name}'")

        username = self.generate_username(
            name, existing_usernames + existing_usernames_in_mo
        )
        logger.info(
            "Generated username based on name",
            givenname=givenname,
            surname=surname,
            username=username,
        )

        dn = self._make_dn(common_name)
        employee_attributes = await self._get_employee_ldap_attributes(employee, dn)
        other_attributes = {
            "sAMAccountName": username,
            "userPrincipalName": f"{username}@alleroed.dk",
        }

        await self.dataloader.ldapapi.add_ldap_object(
            dn,
            employee_attributes | other_attributes,
        )

        return dn


def get_username_generator_class(
    username_generator: str,
) -> type[UserNameGenerator]:
    match username_generator:
        case "UserNameGenerator":
            return UserNameGenerator
        case "AlleroedUserNameGenerator":
            return AlleroedUserNameGenerator
        case _:
            raise ValueError("No such username_generator")
