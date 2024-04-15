from uuid import UUID

from .base_model import BaseModel


class EmployeeCreate(BaseModel):
    employee_create: "EmployeeCreateEmployeeCreate"


class EmployeeCreateEmployeeCreate(BaseModel):
    uuid: UUID


EmployeeCreate.update_forward_refs()
EmployeeCreateEmployeeCreate.update_forward_refs()
