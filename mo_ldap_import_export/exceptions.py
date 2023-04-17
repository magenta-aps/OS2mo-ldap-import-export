# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
from fastapi import HTTPException

from .logging import logger


class MultipleObjectsReturnedException(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)
        logger.exception(message)


class NoObjectsReturnedException(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)
        logger.exception(message)


class AttributeNotFound(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)
        logger.exception(message)


class CPRFieldNotFound(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)
        logger.exception(message)


class IncorrectMapping(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=400, detail=message)
        logger.exception(message)


class NotSupportedException(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)
        logger.exception(message)


class InvalidNameException(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)
        logger.exception(message)


class UUIDNotFoundException(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)


class InvalidQueryResponse(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)


class InvalidQuery(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)


class TimeOutException(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)


class IgnoreChanges(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)


class InvalidChangeDict(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)


class InvalidCPR(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=422, detail=message)


class DNNotFound(HTTPException):
    def __init__(self, message):
        super().__init__(status_code=404, detail=message)
