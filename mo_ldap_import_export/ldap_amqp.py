# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
from typing import Annotated

import structlog
from fastapi import APIRouter
from fastapi import Body
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi import status
from fastramqpi.main import FastRAMQPI
from fastramqpi.ramqp import AMQPSystem
from fastramqpi.ramqp.amqp import Router
from fastramqpi.ramqp.depends import rate_limit

from .amqp_to_http import gen_handler
from .config import LDAPAMQPConnectionSettings
from .depends import SyncTool
from .depends import logger_bound_message_id
from .exceptions import NoObjectsReturnedException
from .types import DN

logger = structlog.stdlib.get_logger()


ldap_amqp_router = Router()
ldap_router = APIRouter()

# Try errors again after a short period of time
delay_on_error = 10


@ldap_router.post("/process_dn", status_code=200)
async def process_dn_http(
    sync_tool: SyncTool,
    request: Request,
    dn: Annotated[DN, Body()],
) -> None:
    print(request.__dict__)
    print(request.state.__dict__)

    # TODO: Convert payload to entityUUID / ADGUID?
    logger.info("Received LDAP HTTP event", dn=dn)
    try:
        await sync_tool.import_single_user(dn)
    except NoObjectsReturnedException as exc:
        # TODO: Stop rejecting these and actually handle it within the code
        logger.exception("Throwing away message due to bad code")
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail="Reject message",
        ) from exc


ldap_amqp_router.register("dn")(gen_handler(url="/process_dn", name="process_dn"))


def configure_ldap_amqpsystem(
    fastramqpi: FastRAMQPI, settings: LDAPAMQPConnectionSettings, priority: int
) -> None:
    logger.info("Initializing LDAP AMQP system")
    ldap_amqpsystem = AMQPSystem(
        settings=settings,
        router=ldap_amqp_router,
        dependencies=[
            Depends(rate_limit(delay_on_error)),
        ],
    )
    fastramqpi.add_context(ldap_amqpsystem=ldap_amqpsystem)
    # Needs to run after SyncTool
    # TODO: Implement a dependency graph?
    fastramqpi.add_lifespan_manager(ldap_amqpsystem, priority)
    ldap_amqpsystem.router.registry.update(ldap_amqp_router.registry)
    ldap_amqpsystem.context = fastramqpi._context

    app = fastramqpi.get_app()
    app.include_router(
        ldap_router,
        dependencies=[Depends(logger_bound_message_id)],
    )
