# SPDX-FileCopyrightText: Magenta ApS
# SPDX-License-Identifier: MPL-2.0
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from mo_ldap_import_export.config import Settings


def get_db_url(settings: Settings) -> str:
    return f"postgresql://{settings.db.user}:{settings.db.password.get_secret_value()}@{settings.db.pghost}/{settings.db.database_name}"


def get_engine() -> Engine:
    settings = Settings()
    return create_engine(get_db_url(settings))
