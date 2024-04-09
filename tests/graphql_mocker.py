# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
"""Respx helpers for mocking GraphQL endpoints."""
from typing import cast

from fastapi.encoders import jsonable_encoder
from httpx import Response
from respx import MockRouter
from respx import Route


class GraphQLRoute(Route):
    @property
    def result(self):
        return self._return_value.json()["data"]

    @result.setter
    def result(self, value) -> None:
        # TODO: Support errors
        self._return_value = Response(200, json={"data": jsonable_encoder(value)})


class GraphQLMocker(MockRouter):
    # NOTE: Copied from the respx source-code
    #       Only change is the constructed route-type
    def route(self, *patterns, name=None, **lookups) -> GraphQLRoute:
        route = GraphQLRoute(*patterns, **lookups)
        return cast(GraphQLRoute, self.add(route, name=name))

    # New mocking method, matching on GraphQL query name
    def query(self, query_name: str) -> GraphQLRoute:
        # TODO: Match more strictly on query name
        return cast(GraphQLRoute, self.post(None, content__contains=query_name))
