# SPDX-FileCopyrightText: Magenta ApS
# SPDX-License-Identifier: MPL-2.0
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from db.config import DBsettings


def get_db_url(settings: DBsettings) -> str:
    return f"postgresql://{settings.app_dbuser}:{settings.app_dbpassword.get_secret_value()}@{settings.pghost}/{settings.app_database}"


def get_engine() -> Engine:
    settings = DBsettings()
    return create_engine(get_db_url(settings))
