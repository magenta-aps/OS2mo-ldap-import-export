# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
import structlog
from structlog.contextvars import merge_contextvars

from .processors import mask_cpr

logger = structlog.wrap_logger(
    structlog.get_logger(),
    processors=[merge_contextvars, mask_cpr, structlog.dev.ConsoleRenderer()],
)
