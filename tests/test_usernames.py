# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
from collections.abc import Iterator
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastramqpi.context import Context
from pydantic import ValidationError
from pydantic import parse_obj_as
from ramodels.mo import Employee

from mo_ldap_import_export.config import Settings
from mo_ldap_import_export.config import UsernameGeneratorConfig
from mo_ldap_import_export.depends import GraphQLClient
from mo_ldap_import_export.moapi import MOAPI
from mo_ldap_import_export.usernames import AlleroedUserNameGenerator
from mo_ldap_import_export.usernames import UserNameGenerator
from tests.graphql_mocker import GraphQLMocker


@pytest.fixture
def dataloader() -> MagicMock:
    mock = MagicMock()
    mock.load_all_it_users = AsyncMock()
    mock.ldapapi.add_ldap_object = AsyncMock()
    return mock


@pytest.fixture
def context(dataloader: MagicMock, converter: MagicMock) -> Context:
    mapping = {
        "mo_to_ldap": {"Employee": {}},
        "username_generator": {
            "objectClass": "UserNameGenerator",
            "char_replacement": {"ø": "oe", "æ": "ae", "å": "aa"},
            "forbidden_usernames": ["holes", "hater"],
            "combinations_to_try": ["F123L", "F12LL", "F1LLL", "FLLLL", "FLLLLX"],
        },
    }

    settings_mock = MagicMock()
    settings_mock.ldap_search_base = "DC=bar"
    settings_mock.ldap_dialect = "AD"
    settings_mock.ldap_ou_for_new_users = ""

    ldap_connection = AsyncMock()

    context: Context = {
        "user_context": {
            "mapping": mapping,
            "settings": settings_mock,
            "dataloader": dataloader,
            "converter": converter,
            "ldap_connection": ldap_connection,
        }
    }

    return context


@pytest.fixture
def existing_usernames() -> list:
    return ["nj", "ngc"]


@pytest.fixture
def existing_common_names() -> list:
    return ["Nick Janssen", "Nick Janssen_2"]


@pytest.fixture
def existing_user_principal_names() -> list:
    return ["nj@magenta.dk", "ngc2@magenta.dk"]


@pytest.fixture
def existing_usernames_ldap(
    existing_usernames, existing_common_names, existing_user_principal_names
) -> list:
    existing_usernames_ldap = [
        {"attributes": {"cn": cn, "sAMAccountName": sam, "userPrincipalName": up}}
        for cn, sam, up in zip(
            existing_common_names,
            existing_usernames,
            existing_user_principal_names,
            strict=False,
        )
    ]
    return existing_usernames_ldap


@pytest.fixture
def username_generator(
    context: Context, existing_usernames_ldap: list
) -> Iterator[UserNameGenerator]:
    with patch(
        "mo_ldap_import_export.usernames.paged_search",
        return_value=existing_usernames_ldap,
    ):
        user_context = context["user_context"]
        yield UserNameGenerator(
            context,
            user_context["settings"],
            parse_obj_as(
                UsernameGeneratorConfig, user_context["mapping"]["username_generator"]
            ),
            user_context["dataloader"],
            user_context["ldap_connection"],
        )


@pytest.fixture
def alleroed_username_generator(
    context: Context, existing_usernames_ldap: list
) -> Iterator[AlleroedUserNameGenerator]:
    context["user_context"]["mapping"] = {}
    context["user_context"]["mapping"]["username_generator"] = {
        "objectClass": "AlleroedUserNameGenerator",
        "char_replacement": {},
        # Note: We need some 'X's in this list. to account for potential duplicates
        # Note2: We need some short combinations in this list, to account for persons with
        # short names.
        #
        # Index:
        # F: First name
        # 1: First middle name
        # 2: Second middle name
        # 3: Third middle name
        # L: Last name
        # X: Number
        #
        # Example1: If combination = "F11LL", 'Hans Jakob Hansen' returns username="hjaha"
        # Example2: If combination = "FFLL", 'Hans Jakob Hansen' returns username="haha"
        "combinations_to_try": [
            # Try to make a username with 4 characters.
            "F111",
            "F112",
            "F122",
            "F222",
            "F223",
            "F233",
            "F333",
            #
            "F11L",
            "F12L",
            "F22L",
            "F23L",
            "F33L",
            #
            "F1LL",
            "F2LL",
            "F3LL",
            #
            "FLLL",
            #
            # If we get to here, we failed to make a username with 4 characters.
            "F111L",
            "F112L",
            "F122L",
            "F222L",
            "F223L",
            "F233L",
            "F333L",
            #
            "F11LL",
            "F12LL",
            "F22LL",
            "F23LL",
            "F33LL",
            #
            "F1LLL",
            "F2LLL",
            "F3LLL",
            #
            "FLLLL",
            #
            # If we get to here, we failed to make a username with only a single
            # character for the first name
            #
            "FF11",
            "FF12",
            "FF22",
            "FF23",
            "FF33",
            "FF1L",
            "FF2L",
            "FF3L",
            "FFLL",
            #
            "FFF1",
            "FFF2",
            "FFF3",
            "FFFL",
            #
            "FFFF",
        ],
        "forbidden_usernames": ["abrn", "anls"],
    }

    with patch(
        "mo_ldap_import_export.usernames.paged_search",
        return_value=existing_usernames_ldap,
    ):
        user_context = context["user_context"]
        yield AlleroedUserNameGenerator(
            context,
            user_context["settings"],
            parse_obj_as(
                UsernameGeneratorConfig, user_context["mapping"]["username_generator"]
            ),
            user_context["dataloader"],
            user_context["ldap_connection"],
        )


async def test_get_existing_usernames(
    username_generator: UserNameGenerator,
    existing_usernames: list,
    existing_common_names: list,
):
    result = await username_generator.get_existing_values(["sAMAccountName", "cn"])
    assert result["sAMAccountName"] == existing_usernames
    assert result["cn"] == [cn.lower() for cn in existing_common_names]


def test_create_username(username_generator: UserNameGenerator):
    # Regular user
    username = username_generator._create_username(["Nick", "Janssen"], [])
    assert username == "njans"

    # User with a funny character
    username = username_generator._create_username(["Nick", "Jænssen"], [])
    assert username == "njaen"

    # User with a funny character which is not in the character replacement mapping
    username = username_generator._create_username(["N1ck", "Janssen"], [])
    assert username == "njans"

    # User with a middle name
    username = username_generator._create_username(["Nick", "Gerardus", "Janssen"], [])
    assert username == "ngjan"

    # User with two middle names
    username = username_generator._create_username(
        ["Nick", "Gerardus", "Cornelis", "Janssen"], []
    )
    assert username == "ngcja"

    # User with three middle names
    username = username_generator._create_username(
        ["Nick", "Gerardus", "Cornelis", "Optimus", "Janssen"], []
    )
    assert username == "ngcoj"

    # User with 4 middle names (only the first three are used)
    username = username_generator._create_username(
        ["Nick", "Gerardus", "Cornelis", "Optimus", "Prime", "Janssen"], []
    )
    assert username == "ngcoj"

    # Simulate case where 'njans' is taken
    username = username_generator._create_username(["Nick", "Janssen"], ["njans"])
    assert username == "njans2"

    # Simulate a case which fits none of the models (last name is too short)
    with pytest.raises(RuntimeError):
        username_generator._create_username(["Nick", "Ja"], [])

    # Simulate a case where a forbidden username is generated
    username = username_generator._create_username(
        ["Harry", "Alexander", "Terpstra"], []
    )
    assert username != "hater"
    assert username == "hterp"


def test_create_common_name(username_generator: UserNameGenerator):
    # Regular case
    common_name = username_generator._create_common_name(["Nick", "Johnson"], [])
    assert common_name == "Nick Johnson"

    # When 'Nick Janssen' already exists and so does 'Nick Janssen_2'
    common_name = username_generator._create_common_name(
        ["Nick", "Janssen"], ["nick janssen", "nick janssen_2"]
    )
    assert common_name == "Nick Janssen_3"

    # Middle names are not used
    common_name = username_generator._create_common_name(
        ["Nick", "Gerardus", "Cornelis", "Johnson"], []
    )
    assert common_name == "Nick Gerardus Cornelis Johnson"

    # Users without a last name are supported
    common_name = username_generator._create_common_name(["Nick", ""], [])
    assert common_name == "Nick"

    # Nick_1 until Nick_2000 exists - we cannot generate a username
    with pytest.raises(RuntimeError):
        username_generator._create_common_name(
            ["Nick", ""], ["nick"] + [f"nick_{d}" for d in range(2000)]
        )

    # If a name is over 64 characters, a middle name is removed.
    common_name = username_generator._create_common_name(
        ["Nick", "Gerardus", "Cornelis", "long name" * 20, "Johnson"], []
    )
    assert common_name == "Nick Gerardus Cornelis Johnson"

    # If the name is still over 64 characters, another middle name is removed.
    common_name = username_generator._create_common_name(
        ["Nick", "Gerardus", "Cornelis", "long name" * 20, "Hansen", "Johnson"], []
    )
    assert common_name == "Nick Gerardus Cornelis Johnson"

    # In the rare case that someone has a first or last name with over 64 characters,
    # we cut off characters from his name
    # Because AD does not allow common names with more than 64 characters
    common_name = username_generator._create_common_name(["Nick" * 40, "Johnson"], [])
    assert common_name == ("Nick" * 40)[:60]

    common_name = username_generator._create_common_name(["Nick", "Johnson" * 40], [])
    assert common_name == ("Nick" + " " + "Johnson" * 40)[:60]

    common_name = username_generator._create_common_name(
        ["Nick", "Gerardus", "Cornelis", "Johnson" * 40], []
    )
    assert common_name == ("Nick" + " " + "Johnson" * 40)[:60]


async def test_generate_dn(username_generator: UserNameGenerator):
    username_generator.settings.conversion_mapping.mo2ldap = None  # type: ignore

    employee = Employee(givenname="Patrick", surname="Bateman")
    dn = await username_generator.generate_dn(employee)
    assert dn == "CN=Patrick Bateman,DC=bar"


def test_create_from_combi(username_generator: UserNameGenerator):
    # Test with a combi that starts with an 'X'
    name = ["Nick", "Janssen"]
    combi = "XFL"
    username = username_generator._create_from_combi(name, combi)
    assert username == "Xnj"

    # Test with a combi that expects 5 characters for the first name
    name = ["Nick", "Janssen"]
    combi = "FFFFFL"
    username = username_generator._create_from_combi(name, combi)
    assert username is None

    # Test with a user without a last name
    name = ["Nick", ""]
    combi = "FFFL"
    username = username_generator._create_from_combi(name, combi)
    assert username is None


def test_check_combinations_to_try():
    config = {"combinations_to_try": ["GAK"]}
    with pytest.raises(ValidationError, match="Incorrect combination"):
        parse_obj_as(UsernameGeneratorConfig, config)


def test_alleroed_username_generator(
    alleroed_username_generator: AlleroedUserNameGenerator,
):
    alleroed_username_generator.forbidden_usernames = []
    existing_names: list[str] = []
    expected_usernames = iter(
        [
            "llkk",
            "llkr",
            "llrs",
            "lrsm",
            "llkkr",
            "llkrs",
            "llrsm",
            "lrsms",
            "lolk",
            "lalk",
            "lelk",
            "lalr",
            "mlxn",
            "mlxb",
            "mlbr",
            "mbrh",
            "mlbn",
            "mbrn",
            "brul",
            "borl",
            "benl",
            "bruc",
            "dobn",
        ]
    )

    for name in [
        ["Lars", "Løkke", "Rasmussen"],
        ["Lone", "Løkke", "Rasmussen"],
        ["Lærke", "Løkke", "Rasmussen"],
        ["Leo", "Løkke", "Rasmussen"],
        ["Lukas", "Løkke", "Rasmussen"],
        ["Liam", "Løkke", "Rasmussen"],
        ["Ludvig", "Løkke", "Rasmussen"],
        ["Laurits", "Løkke", "Rasmussen"],
        ["Loki", "Løkke", "Rasmussen"],
        ["Lasse", "Løkke", "Rasmussen"],
        ["Leonardo", "Løkke", "Rasmussen"],
        ["Laus", "Løkke", "Rasmussen"],
        ["Margrethe", "Alexandrine", "borhildur", "Ingrid"],
        ["Mia", "Alexandrine", "borhildur", "Ingrid"],
        ["Mike", "Alexandrine", "borhildur", "Ingrid"],
        ["Max", "Alexandrine", "borhildur", "Ingrid"],
        ["Mick", "Alexandrine", "borhildur", "Ingrid"],
        ["Mads", "Alexandrine", "borhildur", "Ingrid"],
        ["Bruce", "Lee"],
        ["Boris", "Lee"],
        ["Benjamin", "Lee"],
        ["Bruce", ""],
        ["Dorthe", "Baun"],
    ]:
        username = alleroed_username_generator.generate_username(name, existing_names)
        assert username == next(expected_usernames)
        existing_names.append(username)


async def test_alleroed_dn_generator(
    settings_mock: Settings,
    alleroed_username_generator: AlleroedUserNameGenerator,
    graphql_mock: GraphQLMocker,
) -> None:
    alleroed_username_generator.settings.conversion_mapping.mo2ldap = None  # type: ignore

    graphql_client = GraphQLClient("http://example.com/graphql")

    itsystem_uuid = uuid4()

    route1 = graphql_mock.query("read_all_ituser_user_keys_by_itsystem_uuid")
    route1.result = {"itusers": {"objects": []}}

    route2 = graphql_mock.query("read_itsystem_uuid")
    route2.result = {"itsystems": {"objects": [{"uuid": itsystem_uuid}]}}

    alleroed_username_generator.dataloader.graphql_client = graphql_client  # type: ignore
    alleroed_username_generator.dataloader.moapi = MOAPI(settings_mock, graphql_client)  # type: ignore

    employee = Employee(givenname="Patrick", surname="Bateman")
    dn = await alleroed_username_generator.generate_dn(employee)
    assert dn == "CN=Patrick Bateman,DC=bar"

    assert route1.called
    assert route2.called


def test_alleroed_username_generator_forbidden_names_from_files(
    alleroed_username_generator: AlleroedUserNameGenerator,
):
    # Try to generate a name that is forbidden
    name = ["Anders", "Broon"]
    username = alleroed_username_generator.generate_username(name, [])
    assert username != "abrn"

    name = ["Anders", "Nolus"]
    username = alleroed_username_generator.generate_username(name, [])
    assert username != "anls"

    # Now clean the list of forbidden usernames and try again
    alleroed_username_generator.forbidden_usernames = []

    name = ["Anders", "Broon"]
    username = alleroed_username_generator.generate_username(name, [])
    assert username == "abrn"

    name = ["Anders", "Nolus"]
    username = alleroed_username_generator.generate_username(name, [])
    assert username == "anls"
