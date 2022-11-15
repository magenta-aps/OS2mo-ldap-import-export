# SPDX-FileCopyrightText: 2019-2020 Magenta ApS
#
# SPDX-License-Identifier: MPL-2.0
"""Ldap class definitions"""
from pydantic import BaseModel
from pydantic import Extra


# We don't decide what needs to be in this model. LDAP does
class LdapEmployee(BaseModel, extra=Extra.allow):
    dn: str
    cpr: str
