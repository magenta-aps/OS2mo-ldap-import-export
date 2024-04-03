# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
"""Dependency injection helpers."""
from typing import Annotated
from typing import Any
from typing import AsyncIterable
from typing import Callable

from fastapi import Depends
from fastramqpi.depends import from_user_context
from fastramqpi.ramqp.depends import from_context
from fastramqpi.ramqp.depends import Message
from structlog.contextvars import bound_contextvars

from .autogenerated_graphql_client import GraphQLClient as _GraphQLClient
from .config import Settings as _Settings
from .converters import LdapConverter as _LdapConverter
from .dataloaders import DataLoader as _DataLoader
from .import_export import SyncTool as _SyncTool
from .ldap import Connection as _Connection

GraphQLClient = Annotated[_GraphQLClient, Depends(from_context("graphql_client"))]
SyncTool = Annotated[_SyncTool, Depends(from_user_context("sync_tool"))]
DataLoader = Annotated[_DataLoader, Depends(from_user_context("dataloader"))]
Settings = Annotated[_Settings, Depends(from_user_context("settings"))]
LdapConverter = Annotated[_LdapConverter, Depends(from_user_context("converter"))]
Connection = Annotated[_Connection, Depends(from_user_context("ldap_connection"))]


def get_message_info(field: str) -> Callable:
    async def extractor(message: Message) -> Any:
        return message.info().get(field)

    return extractor


MessageID = Annotated[str | None, Depends(get_message_info("message_id"))]


async def logger_bound_message_id(message_id: MessageID) -> AsyncIterable[None]:
    with bound_contextvars(message_id=message_id):
        yield


LoggerBoundMessageID = Annotated[None, Depends(logger_bound_message_id)]


async def logger_bound_correlation_id(message: Message) -> AsyncIterable[None]:
    correlation_id = await (get_message_info("correlation_id"))(message)
    with bound_contextvars(correlation_id=correlation_id):
        yield


LoggerBoundCorrelationID = Annotated[None, Depends(logger_bound_correlation_id)]
