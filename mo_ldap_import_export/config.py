# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
from pydantic import AmqpDsn
from pydantic import BaseSettings
from pydantic import parse_obj_as


class Settings(BaseSettings):

    amqp_url: AmqpDsn = parse_obj_as(AmqpDsn, "amqp://guest:guest@localhost:5672")
    amqp_exchange: str = "os2mo"
