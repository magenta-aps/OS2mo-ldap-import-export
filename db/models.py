# SPDX-FileCopyrightText: Magenta ApS
# SPDX-License-Identifier: MPL-2.0
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class Runs(Base):  # type: ignore
    __tablename__ = "runs"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    last_run = Column("last_run", DateTime(timezone=True))
