from typing import List
from uuid import UUID

from .base_model import BaseModel


class OrgUnitEngagementPeopleRefresh(BaseModel):
    employee_refresh: "OrgUnitEngagementPeopleRefreshEmployeeRefresh"


class OrgUnitEngagementPeopleRefreshEmployeeRefresh(BaseModel):
    objects: List[UUID]


OrgUnitEngagementPeopleRefresh.update_forward_refs()
OrgUnitEngagementPeopleRefreshEmployeeRefresh.update_forward_refs()
