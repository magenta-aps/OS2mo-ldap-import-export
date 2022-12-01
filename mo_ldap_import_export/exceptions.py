# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
import structlog
from fastapi import HTTPException
from ramqp.utils import RejectMessage

logger = structlog.get_logger()


class MultipleObjectsReturnedException(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)
        logger.exception(message)
        raise RejectMessage()


class NoObjectsReturnedException(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)
        logger.exception(message)
        raise RejectMessage()


class CprNoNotFound(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)
        logger.exception(message)
        raise RejectMessage()


class IncorrectMapping(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=400, detail=message)
        logger.exception(message)
        raise RejectMessage()


class NotSupportedException(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)
        logger.exception(message)
        raise RejectMessage()
