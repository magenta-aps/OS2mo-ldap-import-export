# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
import asyncio
from functools import partial
from typing import Callable

import httpx
import structlog
from fastapi import status
from fastramqpi.ramqp.depends import Message
from fastramqpi.ramqp.utils import RejectMessage
from fastramqpi.ramqp.utils import RequeueMessage

from .depends import App

logger = structlog.stdlib.get_logger()


async def process_dn(
    endpoint_url: str,
    app: App,
    message: Message,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://app/") as client:
        headers = {}
        # TODO: Add more headers based on IncomingMessage as required
        if message.content_type is not None:
            headers["Content-Type"] = message.content_type
        if message.content_encoding is not None:
            headers["Content-Encoding"] = message.content_encoding
        if message.correlation_id is not None:
            headers["X-Correlation-ID"] = message.correlation_id
        if message.message_id is not None:
            headers["X-Message-ID"] = message.message_id
        for key, value in message.headers.items():
            headers[f"X-AMQP-HEADER-{key}"] = str(value)

        logger.info(
            "amqp-to-http request",
            endpoint_url=endpoint_url,
            content=message.body,
            headers=headers,
        )
        response = await client.post(
            endpoint_url, content=message.body, headers=headers
        )
        logger.info(
            "amqp-to-http response",
            status_code=response.status_code,
            content=response.content,
        )

        # Handle legal issues
        if response.status_code in [status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS]:
            raise RejectMessage("We legally cannot process this")

        # Handle status-codes indicating that we may be going too fast
        if response.status_code in [
            status.HTTP_408_REQUEST_TIMEOUT,
            status.HTTP_425_TOO_EARLY,
            status.HTTP_429_TOO_MANY_REQUESTS,
            # TODO: Maybe only sleep on 503 if it is a redelivery?
            status.HTTP_503_SERVICE_UNAVAILABLE,
            status.HTTP_504_GATEWAY_TIMEOUT,
        ]:
            # TODO: Maybe the response should contain the sleep time?
            await asyncio.sleep(30)
            raise RequeueMessage("Was going too fast")

        # All 200 status-codes are OK
        if 200 <= response.status_code < 300:
            return

        # TODO: Do we want to reject or requeue this?
        if response.status_code in [status.HTTP_501_NOT_IMPLEMENTED]:
            raise RequeueMessage("Not implemented")

        # Any 400 code means we need to reject the message
        # TODO: We should probably distinguish bad AMQP events from bad forwards?
        if 400 <= response.status_code < 500:
            # NOTE: All of these should probably be deadlettered in the future
            raise RequeueMessage("We send a bad request")
        # Any other 500 code means we need to retry
        if 500 <= response.status_code < 600:
            raise RequeueMessage("The server done goofed")

        # We intentionally do not handle 100 and 300 codes
        # If we got a 300 code it is probably a misconfiguration
        # NOTE: All of these should probably be deadlettered in the future
        raise RequeueMessage(f"Unexpected status-code: {response.status_code}")


def gen_handler(
    url: str,
    name: str,
) -> Callable[[App, Message], None]:
    callable = partial(process_dn, url)
    callable.__name__ = name
    return callable
