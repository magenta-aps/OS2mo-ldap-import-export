# SPDX-FileCopyrightText: Magenta ApS
# SPDX-License-Identifier: MPL-2.0
from sqlalchemy import Column, String
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy.dialects.postgresql import TEXT
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func


Base = declarative_base()

class Runs(Base):  # type: ignore
    __tablename__ = "runs"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    last_run = Column("last_run", DateTime(timezone=True))
    
