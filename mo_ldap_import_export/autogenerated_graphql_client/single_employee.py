# Generated by ariadne-codegen on 2023-08-14 15:18
# Source: queries.graphql

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import Field

from .base_model import BaseModel


class SingleEmployee(BaseModel):
    employees: "SingleEmployeeEmployees"


class SingleEmployeeEmployees(BaseModel):
    objects: List["SingleEmployeeEmployeesObjects"]


class SingleEmployeeEmployeesObjects(BaseModel):
    objects: List["SingleEmployeeEmployeesObjectsObjects"]


class SingleEmployeeEmployeesObjectsObjects(BaseModel):
    uuid: UUID
    cpr_no: Optional[Any]
    givenname: str
    surname: str
    nickname_givenname: Optional[str]
    nickname_surname: Optional[str]
    validity: "SingleEmployeeEmployeesObjectsObjectsValidity"


class SingleEmployeeEmployeesObjectsObjectsValidity(BaseModel):
    to: Optional[datetime]
    from_: Optional[datetime] = Field(alias="from")


SingleEmployee.update_forward_refs()
SingleEmployeeEmployees.update_forward_refs()
SingleEmployeeEmployeesObjects.update_forward_refs()
SingleEmployeeEmployeesObjectsObjects.update_forward_refs()
SingleEmployeeEmployeesObjectsObjectsValidity.update_forward_refs()
