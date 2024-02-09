# SPDX-FileCopyrightText: Magenta ApS
# SPDX-License-Identifier: MPL-2.0
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.orm import sessionmaker

from db.engine import get_engine
from db.models import Runs


Session = sessionmaker()


def persist_status(timestamp: datetime) -> None:
    Session.configure(bind=get_engine())
    session = Session()
    run = Runs(last_run=timestamp)
    session.add(run)
    session.commit()


def get_run_db_last_run() -> datetime:
    Session.configure(bind=get_engine())
    session = Session()
    # Note: we use the last to_date as the new from_date
    statement = select(max(Runs.last_run))
    from_date = session.scalar_one_or_none(statement)
    return from_date
