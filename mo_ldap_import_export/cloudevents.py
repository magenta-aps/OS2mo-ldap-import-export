# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
"""CloudEvent handling."""
from typing import Annotated
from uuid import UUID

import structlog
from cloudevents.pydantic import CloudEvent
from cloudevents.pydantic import from_http
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request

logger = structlog.stdlib.get_logger()


async def cloudevent(request: Request) -> CloudEvent:
    return from_http(request.headers, await request.body())


def assert_event_type(event_types: set[str]):
    async def checker(event: Annotated[CloudEvent, Depends(cloudevent)]) -> None:
        if event.type not in event_types:
            logger.warning(
                "Invalid event type", received=event.type, expected=event_types
            )
            raise HTTPException(400, detail="Invalid event type")

    return checker


async def event2uuid(event: Annotated[CloudEvent, Depends(cloudevent)]) -> UUID:
    return UUID(event.data)
