# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
# SPDX-License-Identifier: MPL-2.0
from typing import Annotated

from fastapi import Depends
from fastramqpi.depends import from_user_context

from .config import Settings as Settings_

Settings = Annotated[Settings_, Depends(from_user_context("settings"))]
