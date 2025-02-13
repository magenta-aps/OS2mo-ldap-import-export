from datetime import datetime
from typing import Any
from typing import Optional
from uuid import UUID

from pydantic import Field

from ..types import CPRNumber
from .base_model import UNSET
from .base_model import BaseModel
from .base_model import UnsetType
from .enums import AuditLogModel
from .enums import FileStore
from .enums import OwnerInferencePriority


class AddressCreateInput(BaseModel):
    uuid: UUID | None = None
    org_unit: UUID | None = None
    person: UUID | None = None
    employee: UUID | None = None
    engagement: UUID | None = None
    ituser: UUID | None = None
    visibility: UUID | None = None
    validity: "RAValidityInput | UnsetType" = UNSET
    user_key: str | None = None
    value: str | UnsetType = UNSET
    address_type: UUID | UnsetType = UNSET


class AddressFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    registration: Optional["AddressRegistrationFilter"] = None
    address_type: Optional["ClassFilter"] = None
    address_types: list[UUID] | None = None
    address_type_user_keys: list[str] | None = None
    engagement: Optional["EngagementFilter"] = None
    engagements: list[UUID] | None = None
    ituser: Optional["ITUserFilter"] = None
    visibility: Optional["ClassFilter"] = None


class AddressRegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class AddressTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class AddressUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    org_unit: UUID | None = None
    person: UUID | None = None
    employee: UUID | None = None
    engagement: UUID | None = None
    ituser: UUID | None = None
    visibility: UUID | None = None
    validity: "RAValidityInput | UnsetType" = UNSET
    user_key: str | None = None
    value: str | None = None
    address_type: UUID | None = None


class AssociationCreateInput(BaseModel):
    uuid: UUID | None = None
    user_key: str | None = None
    primary: UUID | None = None
    validity: "RAValidityInput | UnsetType" = UNSET
    person: UUID | None = None
    employee: UUID | None = None
    substitute: UUID | None = None
    trade_union: UUID | None = None
    org_unit: UUID | UnsetType = UNSET
    association_type: UUID | UnsetType = UNSET


class AssociationFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    registration: Optional["AssociationRegistrationFilter"] = None
    association_type: Optional["ClassFilter"] = None
    association_types: list[UUID] | None = None
    association_type_user_keys: list[str] | None = None
    it_association: bool | None = None


class AssociationRegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class AssociationTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class AssociationUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    user_key: str | None = None
    primary: UUID | None = None
    validity: "RAValidityInput | UnsetType" = UNSET
    person: UUID | None = None
    employee: UUID | None = None
    substitute: UUID | None = None
    trade_union: UUID | None = None
    org_unit: UUID | None = None
    association_type: UUID | None = None


class AuditLogFilter(BaseModel):
    ids: list[UUID] | None = None
    uuids: list[UUID] | None = None
    actors: list[UUID] | None = None
    models: list[AuditLogModel] | None = None
    start: datetime | None = None
    end: datetime | None = None


class ClassCreateInput(BaseModel):
    uuid: UUID | None = None
    name: str | UnsetType = UNSET
    user_key: str | UnsetType = UNSET
    facet_uuid: UUID | UnsetType = UNSET
    scope: str | None = None
    published: str = "Publiceret"
    parent_uuid: UUID | None = None
    example: str | None = None
    owner: UUID | None = None
    validity: "ValidityInput | UnsetType" = UNSET
    it_system_uuid: UUID | None = None


class ClassFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["ClassRegistrationFilter"] = None
    facet: Optional["FacetFilter"] = None
    facets: list[UUID] | None = None
    facet_user_keys: list[str] | None = None
    parent: Optional["ClassFilter"] = None
    parents: list[UUID] | None = None
    parent_user_keys: list[str] | None = None
    it_system: Optional["ITSystemFilter"] = None
    owner: Optional["ClassOwnerFilter"] = None
    scope: list[str] | None = None


class ClassOwnerFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["OrganisationUnitRegistrationFilter"] = None
    query: str | None | UnsetType = UNSET
    names: list[str] | None | UnsetType = UNSET
    parent: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    parents: list[UUID] | None | UnsetType = UNSET
    child: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    hierarchy: Optional["ClassFilter"] = None
    hierarchies: list[UUID] | None = None
    subtree: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    descendant: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    ancestor: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    engagement: Optional["EngagementFilter"] = None
    include_none: bool = False


class ClassRegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class ClassTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class ClassUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    name: str | UnsetType = UNSET
    user_key: str | UnsetType = UNSET
    facet_uuid: UUID | UnsetType = UNSET
    scope: str | None = None
    published: str = "Publiceret"
    parent_uuid: UUID | None = None
    example: str | None = None
    owner: UUID | None = None
    validity: "ValidityInput | UnsetType" = UNSET
    it_system_uuid: UUID | None = None


class ConfigurationFilter(BaseModel):
    identifiers: list[str] | None = None


class EmployeeCreateInput(BaseModel):
    uuid: UUID | None = None
    user_key: str | None = None
    nickname_given_name: str | None = None
    nickname_surname: str | None = None
    seniority: Any | None = None
    cpr_number: CPRNumber | None = None
    given_name: str | UnsetType = UNSET
    surname: str | UnsetType = UNSET


class EmployeeFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["EmployeeRegistrationFilter"] = None
    query: str | None | UnsetType = UNSET
    cpr_numbers: list[CPRNumber] | None = None


class EmployeeRegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class EmployeeTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET
    vacate: bool = False


class EmployeeUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    user_key: str | None = None
    nickname_given_name: str | None = None
    nickname_surname: str | None = None
    seniority: Any | None = None
    cpr_number: CPRNumber | None = None
    given_name: str | None = None
    surname: str | None = None
    validity: "RAValidityInput | UnsetType" = UNSET


class EmployeesBoundAddressFilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["AddressRegistrationFilter"] = None
    address_type: Optional["ClassFilter"] = None
    address_types: list[UUID] | None = None
    address_type_user_keys: list[str] | None = None
    engagement: Optional["EngagementFilter"] = None
    engagements: list[UUID] | None = None
    ituser: Optional["ITUserFilter"] = None
    visibility: Optional["ClassFilter"] = None


class EmployeesBoundAssociationFilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["AssociationRegistrationFilter"] = None
    association_type: Optional["ClassFilter"] = None
    association_types: list[UUID] | None = None
    association_type_user_keys: list[str] | None = None
    it_association: bool | None = None


class EmployeesBoundEngagementFilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["EngagementRegistrationFilter"] = None
    job_function: Optional["ClassFilter"] = None
    engagement_type: Optional["ClassFilter"] = None


class EmployeesBoundITUserFilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["ITUserRegistrationFilter"] = None
    itsystem: Optional["ITSystemFilter"] = None
    itsystem_uuids: list[UUID] | None = None
    engagement: Optional["EngagementFilter"] = None
    external_ids: list[str] | None = None


class EmployeesBoundLeaveFilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["LeaveRegistrationFilter"] = None


class EmployeesBoundManagerFilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["ManagerRegistrationFilter"] = None
    responsibility: Optional["ClassFilter"] = None
    exclude: Optional["EmployeeFilter"] = None


class EngagementCreateInput(BaseModel):
    uuid: UUID | None = None
    user_key: str | None = None
    primary: UUID | None = None
    validity: "RAValidityInput | UnsetType" = UNSET
    extension_1: str | None = None
    extension_2: str | None = None
    extension_3: str | None = None
    extension_4: str | None = None
    extension_5: str | None = None
    extension_6: str | None = None
    extension_7: str | None = None
    extension_8: str | None = None
    extension_9: str | None = None
    extension_10: str | None = None
    employee: UUID | None = None
    person: UUID | None = None
    org_unit: UUID | UnsetType = UNSET
    engagement_type: UUID | UnsetType = UNSET
    job_function: UUID | UnsetType = UNSET


class EngagementFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    registration: Optional["EngagementRegistrationFilter"] = None
    job_function: Optional["ClassFilter"] = None
    engagement_type: Optional["ClassFilter"] = None


class EngagementRegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class EngagementTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class EngagementUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    user_key: str | None = None
    primary: UUID | None = None
    validity: "RAValidityInput | UnsetType" = UNSET
    extension_1: str | None = None
    extension_2: str | None = None
    extension_3: str | None = None
    extension_4: str | None = None
    extension_5: str | None = None
    extension_6: str | None = None
    extension_7: str | None = None
    extension_8: str | None = None
    extension_9: str | None = None
    extension_10: str | None = None
    employee: UUID | None = None
    person: UUID | None = None
    org_unit: UUID | None = None
    engagement_type: UUID | None = None
    job_function: UUID | None = None


class FacetCreateInput(BaseModel):
    uuid: UUID | None = None
    user_key: str | UnsetType = UNSET
    published: str = "Publiceret"
    validity: "ValidityInput | UnsetType" = UNSET


class FacetFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["FacetRegistrationFilter"] = None
    parent: Optional["FacetFilter"] = None
    parents: list[UUID] | None = None
    parent_user_keys: list[str] | None = None


class FacetRegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class FacetTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class FacetUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    user_key: str | UnsetType = UNSET
    published: str = "Publiceret"
    validity: "ValidityInput | UnsetType" = UNSET


class FacetsBoundClassFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["ClassRegistrationFilter"] = None
    facet: Optional["FacetFilter"] = None
    facet_user_keys: list[str] | None = None
    parent: Optional["ClassFilter"] = None
    parents: list[UUID] | None = None
    parent_user_keys: list[str] | None = None
    it_system: Optional["ITSystemFilter"] = None
    owner: Optional["ClassOwnerFilter"] = None
    scope: list[str] | None = None


class FileFilter(BaseModel):
    file_store: FileStore | UnsetType = UNSET
    file_names: list[str] | None = None


class HealthFilter(BaseModel):
    identifiers: list[str] | None = None


class ITAssociationCreateInput(BaseModel):
    uuid: UUID | None = None
    user_key: str | None = None
    primary: UUID | None = None
    validity: "RAValidityInput | UnsetType" = UNSET
    org_unit: UUID | UnsetType = UNSET
    person: UUID | UnsetType = UNSET
    it_user: UUID | UnsetType = UNSET
    job_function: UUID | UnsetType = UNSET


class ITAssociationTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class ITAssociationUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    user_key: str | None = None
    primary: UUID | None = None
    validity: "RAValidityInput | UnsetType" = UNSET
    org_unit: UUID | None = None
    it_user: UUID | None = None
    job_function: UUID | None = None


class ITSystemCreateInput(BaseModel):
    uuid: UUID | None = None
    user_key: str | UnsetType = UNSET
    name: str | UnsetType = UNSET
    validity: "RAOpenValidityInput | UnsetType" = UNSET


class ITSystemFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["ITSystemRegistrationFilter"] = None


class ITSystemRegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class ITSystemTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class ITSystemUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    user_key: str | UnsetType = UNSET
    name: str | UnsetType = UNSET
    validity: "RAOpenValidityInput | UnsetType" = UNSET


class ITUserCreateInput(BaseModel):
    uuid: UUID | None = None
    external_id: str | None = None
    primary: UUID | None = None
    person: UUID | None = None
    org_unit: UUID | None = None
    engagement: UUID | None = None
    validity: "RAValidityInput | UnsetType" = UNSET
    user_key: str | UnsetType = UNSET
    itsystem: UUID | UnsetType = UNSET
    note: str | None = None


class ITUserFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    registration: Optional["ITUserRegistrationFilter"] = None
    itsystem: Optional["ITSystemFilter"] = None
    itsystem_uuids: list[UUID] | None = None
    engagement: Optional["EngagementFilter"] = None
    external_ids: list[str] | None = None


class ITUserRegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class ITUserTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class ITUserUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    external_id: str | None = None
    primary: UUID | None = None
    person: UUID | None = None
    org_unit: UUID | None = None
    engagement: UUID | None = None
    validity: "RAValidityInput | UnsetType" = UNSET
    user_key: str | None = None
    itsystem: UUID | None = None
    note: str | None = None


class ItuserBoundAddressFilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["AddressRegistrationFilter"] = None
    address_type: Optional["ClassFilter"] = None
    address_types: list[UUID] | None = None
    address_type_user_keys: list[str] | None = None
    engagement: Optional["EngagementFilter"] = None
    engagements: list[UUID] | None = None
    visibility: Optional["ClassFilter"] = None


class ItuserBoundRoleBindingFilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["RoleRegistrationFilter"] = None


class KLECreateInput(BaseModel):
    uuid: UUID | None = None
    user_key: str | None = None
    org_unit: UUID | UnsetType = UNSET
    kle_aspects: list[UUID] | UnsetType = UNSET
    kle_number: UUID | UnsetType = UNSET
    validity: "RAValidityInput | UnsetType" = UNSET


class KLEFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    registration: Optional["KLERegistrationFilter"] = None


class KLERegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class KLETerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class KLEUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    user_key: str | None = None
    kle_number: UUID | None = None
    kle_aspects: list[UUID] | None = None
    org_unit: UUID | None = None
    validity: "RAValidityInput | UnsetType" = UNSET


class LeaveCreateInput(BaseModel):
    uuid: UUID | None = None
    user_key: str | None = None
    person: UUID | UnsetType = UNSET
    engagement: UUID | UnsetType = UNSET
    leave_type: UUID | UnsetType = UNSET
    validity: "RAValidityInput | UnsetType" = UNSET


class LeaveFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    registration: Optional["LeaveRegistrationFilter"] = None


class LeaveRegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class LeaveTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class LeaveUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    user_key: str | None = None
    person: UUID | None = None
    engagement: UUID | None = None
    leave_type: UUID | None = None
    validity: "RAValidityInput | UnsetType" = UNSET


class ManagerCreateInput(BaseModel):
    uuid: UUID | None = None
    user_key: str | None = None
    person: UUID | None = None
    responsibility: list[UUID] | UnsetType = UNSET
    org_unit: UUID | UnsetType = UNSET
    manager_level: UUID | UnsetType = UNSET
    manager_type: UUID | UnsetType = UNSET
    validity: "RAValidityInput | UnsetType" = UNSET


class ManagerFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    registration: Optional["ManagerRegistrationFilter"] = None
    responsibility: Optional["ClassFilter"] = None
    exclude: Optional["EmployeeFilter"] = None


class ManagerRegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class ManagerTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class ManagerUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    validity: "RAValidityInput | UnsetType" = UNSET
    user_key: str | None = None
    person: UUID | None = None
    responsibility: list[UUID] | None = None
    org_unit: UUID | None = None
    manager_type: UUID | None = None
    manager_level: UUID | None = None


class ModelsUuidsBoundRegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class OrgUnitsboundaddressfilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["AddressRegistrationFilter"] = None
    address_type: Optional["ClassFilter"] = None
    address_types: list[UUID] | None = None
    address_type_user_keys: list[str] | None = None
    engagement: Optional["EngagementFilter"] = None
    engagements: list[UUID] | None = None
    ituser: Optional["ITUserFilter"] = None
    visibility: Optional["ClassFilter"] = None


class OrgUnitsboundassociationfilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["AssociationRegistrationFilter"] = None
    association_type: Optional["ClassFilter"] = None
    association_types: list[UUID] | None = None
    association_type_user_keys: list[str] | None = None
    it_association: bool | None = None


class OrgUnitsboundengagementfilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["EngagementRegistrationFilter"] = None
    job_function: Optional["ClassFilter"] = None
    engagement_type: Optional["ClassFilter"] = None


class OrgUnitsboundituserfilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["ITUserRegistrationFilter"] = None
    itsystem: Optional["ITSystemFilter"] = None
    itsystem_uuids: list[UUID] | None = None
    engagement: Optional["EngagementFilter"] = None
    external_ids: list[str] | None = None


class OrgUnitsboundklefilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["KLERegistrationFilter"] = None


class OrgUnitsboundleavefilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["LeaveRegistrationFilter"] = None


class OrgUnitsboundmanagerfilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["ManagerRegistrationFilter"] = None
    responsibility: Optional["ClassFilter"] = None
    exclude: Optional["EmployeeFilter"] = None


class OrgUnitsboundrelatedunitfilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET


class OrganisationCreate(BaseModel):
    municipality_code: int | None | UnsetType = UNSET


class OrganisationUnitCreateInput(BaseModel):
    uuid: UUID | None | UnsetType = UNSET
    validity: "RAValidityInput | UnsetType" = UNSET
    name: str | UnsetType = UNSET
    user_key: str | None | UnsetType = UNSET
    parent: UUID | None | UnsetType = UNSET
    org_unit_type: UUID | UnsetType = UNSET
    time_planning: UUID | None | UnsetType = UNSET
    org_unit_level: UUID | None | UnsetType = UNSET
    org_unit_hierarchy: UUID | None | UnsetType = UNSET


class OrganisationUnitFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["OrganisationUnitRegistrationFilter"] = None
    query: str | None | UnsetType = UNSET
    names: list[str] | None | UnsetType = UNSET
    parent: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    parents: list[UUID] | None | UnsetType = UNSET
    child: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    hierarchy: Optional["ClassFilter"] = None
    hierarchies: list[UUID] | None = None
    subtree: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    descendant: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    ancestor: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    engagement: Optional["EngagementFilter"] = None


class OrganisationUnitRegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class OrganisationUnitTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class OrganisationUnitUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    validity: "RAValidityInput | UnsetType" = UNSET
    name: str | None | UnsetType = UNSET
    user_key: str | None | UnsetType = UNSET
    parent: UUID | None | UnsetType = UNSET
    org_unit_type: UUID | None | UnsetType = UNSET
    org_unit_level: UUID | None | UnsetType = UNSET
    org_unit_hierarchy: UUID | None | UnsetType = UNSET
    time_planning: UUID | None | UnsetType = UNSET


class OwnerCreateInput(BaseModel):
    uuid: UUID | None = None
    user_key: str | None = None
    org_unit: UUID | None = None
    person: UUID | None = None
    owner: UUID | None = None
    inference_priority: OwnerInferencePriority | None = None
    validity: "RAValidityInput | UnsetType" = UNSET


class OwnerFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    owner: Optional["EmployeeFilter"] = None


class OwnerTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class OwnerUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    user_key: str | None = None
    org_unit: UUID | None = None
    person: UUID | None = None
    owner: UUID | None = None
    inference_priority: OwnerInferencePriority | None = None
    validity: "RAValidityInput | UnsetType" = UNSET


class ParentsBoundClassFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["ClassRegistrationFilter"] = None
    facet: Optional["FacetFilter"] = None
    facets: list[UUID] | None = None
    facet_user_keys: list[str] | None = None
    parent: Optional["ClassFilter"] = None
    parent_user_keys: list[str] | None = None
    it_system: Optional["ITSystemFilter"] = None
    owner: Optional["ClassOwnerFilter"] = None
    scope: list[str] | None = None


class ParentsBoundFacetFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["FacetRegistrationFilter"] = None
    parent: Optional["FacetFilter"] = None
    parent_user_keys: list[str] | None = None


class ParentsBoundOrganisationUnitFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["OrganisationUnitRegistrationFilter"] = None
    query: str | None | UnsetType = UNSET
    names: list[str] | None | UnsetType = UNSET
    parent: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    child: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    hierarchy: Optional["ClassFilter"] = None
    hierarchies: list[UUID] | None = None
    subtree: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    descendant: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    ancestor: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    engagement: Optional["EngagementFilter"] = None


class RAOpenValidityInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | None = None


class RAValidityInput(BaseModel):
    from_: datetime = Field(alias="from")
    to: datetime | None = None


class RegistrationFilter(BaseModel):
    uuids: list[UUID] | None = None
    actors: list[UUID] | None = None
    models: list[str] | None = None
    start: datetime | None = None
    end: datetime | None = None


class RelatedUnitFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None


class RelatedUnitsUpdateInput(BaseModel):
    uuid: UUID | None = None
    origin: UUID | UnsetType = UNSET
    destination: list[UUID] | None = None
    validity: "RAValidityInput | UnsetType" = UNSET


class RoleBindingCreateInput(BaseModel):
    uuid: UUID | None = None
    user_key: str | None = None
    org_unit: UUID | None = None
    ituser: UUID | UnsetType = UNSET
    role: UUID | UnsetType = UNSET
    validity: "RAValidityInput | UnsetType" = UNSET


class RoleBindingFilter(BaseModel):
    uuids: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    registration: Optional["RoleRegistrationFilter"] = None
    ituser: Optional["ITUserFilter"] = None


class RoleBindingTerminateInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | UnsetType = UNSET
    uuid: UUID | UnsetType = UNSET


class RoleBindingUpdateInput(BaseModel):
    uuid: UUID | UnsetType = UNSET
    user_key: str | None = None
    org_unit: UUID | None = None
    ituser: UUID | UnsetType = UNSET
    role: UUID | None = None
    validity: "RAValidityInput | UnsetType" = UNSET


class RoleRegistrationFilter(BaseModel):
    actors: list[UUID] | None = None
    start: datetime | None = None
    end: datetime | None = None


class UuidsBoundClassFilter(BaseModel):
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["ClassRegistrationFilter"] = None
    facet: Optional["FacetFilter"] = None
    facets: list[UUID] | None = None
    facet_user_keys: list[str] | None = None
    parent: Optional["ClassFilter"] = None
    parents: list[UUID] | None = None
    parent_user_keys: list[str] | None = None
    it_system: Optional["ITSystemFilter"] = None
    owner: Optional["ClassOwnerFilter"] = None
    scope: list[str] | None = None


class UuidsBoundEmployeeFilter(BaseModel):
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["EmployeeRegistrationFilter"] = None
    query: str | None | UnsetType = UNSET
    cpr_numbers: list[CPRNumber] | None = None


class UuidsBoundEngagementFilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["EngagementRegistrationFilter"] = None
    job_function: Optional["ClassFilter"] = None
    engagement_type: Optional["ClassFilter"] = None


class UuidsBoundFacetFilter(BaseModel):
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["FacetRegistrationFilter"] = None
    parent: Optional["FacetFilter"] = None
    parents: list[UUID] | None = None
    parent_user_keys: list[str] | None = None


class UuidsBoundITSystemFilter(BaseModel):
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["ITSystemRegistrationFilter"] = None


class UuidsBoundITUserFilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["ITUserRegistrationFilter"] = None
    itsystem: Optional["ITSystemFilter"] = None
    itsystem_uuids: list[UUID] | None = None
    engagement: Optional["EngagementFilter"] = None
    external_ids: list[str] | None = None


class UuidsBoundLeaveFilter(BaseModel):
    org_unit: Optional["OrganisationUnitFilter"] = None
    org_units: list[UUID] | None = None
    employee: Optional["EmployeeFilter"] | UnsetType = UNSET
    employees: list[UUID] | None = None
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["LeaveRegistrationFilter"] = None


class UuidsBoundOrganisationUnitFilter(BaseModel):
    user_keys: list[str] | None = None
    from_date: datetime | None | UnsetType = UNSET
    to_date: datetime | None | UnsetType = UNSET
    registration: Optional["OrganisationUnitRegistrationFilter"] = None
    query: str | None | UnsetType = UNSET
    names: list[str] | None | UnsetType = UNSET
    parent: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    parents: list[UUID] | None | UnsetType = UNSET
    child: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    hierarchy: Optional["ClassFilter"] = None
    hierarchies: list[UUID] | None = None
    subtree: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    descendant: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    ancestor: Optional["OrganisationUnitFilter"] | UnsetType = UNSET
    engagement: Optional["EngagementFilter"] = None


class ValidityInput(BaseModel):
    from_: datetime | None = Field(alias="from", default=None)
    to: datetime | None = None


AddressCreateInput.update_forward_refs()
AddressFilter.update_forward_refs()
AddressRegistrationFilter.update_forward_refs()
AddressTerminateInput.update_forward_refs()
AddressUpdateInput.update_forward_refs()
AssociationCreateInput.update_forward_refs()
AssociationFilter.update_forward_refs()
AssociationRegistrationFilter.update_forward_refs()
AssociationTerminateInput.update_forward_refs()
AssociationUpdateInput.update_forward_refs()
AuditLogFilter.update_forward_refs()
ClassCreateInput.update_forward_refs()
ClassFilter.update_forward_refs()
ClassOwnerFilter.update_forward_refs()
ClassRegistrationFilter.update_forward_refs()
ClassTerminateInput.update_forward_refs()
ClassUpdateInput.update_forward_refs()
ConfigurationFilter.update_forward_refs()
EmployeeCreateInput.update_forward_refs()
EmployeeFilter.update_forward_refs()
EmployeeRegistrationFilter.update_forward_refs()
EmployeeTerminateInput.update_forward_refs()
EmployeeUpdateInput.update_forward_refs()
EmployeesBoundAddressFilter.update_forward_refs()
EmployeesBoundAssociationFilter.update_forward_refs()
EmployeesBoundEngagementFilter.update_forward_refs()
EmployeesBoundITUserFilter.update_forward_refs()
EmployeesBoundLeaveFilter.update_forward_refs()
EmployeesBoundManagerFilter.update_forward_refs()
EngagementCreateInput.update_forward_refs()
EngagementFilter.update_forward_refs()
EngagementRegistrationFilter.update_forward_refs()
EngagementTerminateInput.update_forward_refs()
EngagementUpdateInput.update_forward_refs()
FacetCreateInput.update_forward_refs()
FacetFilter.update_forward_refs()
FacetRegistrationFilter.update_forward_refs()
FacetTerminateInput.update_forward_refs()
FacetUpdateInput.update_forward_refs()
FacetsBoundClassFilter.update_forward_refs()
FileFilter.update_forward_refs()
HealthFilter.update_forward_refs()
ITAssociationCreateInput.update_forward_refs()
ITAssociationTerminateInput.update_forward_refs()
ITAssociationUpdateInput.update_forward_refs()
ITSystemCreateInput.update_forward_refs()
ITSystemFilter.update_forward_refs()
ITSystemRegistrationFilter.update_forward_refs()
ITSystemTerminateInput.update_forward_refs()
ITSystemUpdateInput.update_forward_refs()
ITUserCreateInput.update_forward_refs()
ITUserFilter.update_forward_refs()
ITUserRegistrationFilter.update_forward_refs()
ITUserTerminateInput.update_forward_refs()
ITUserUpdateInput.update_forward_refs()
ItuserBoundAddressFilter.update_forward_refs()
ItuserBoundRoleBindingFilter.update_forward_refs()
KLECreateInput.update_forward_refs()
KLEFilter.update_forward_refs()
KLERegistrationFilter.update_forward_refs()
KLETerminateInput.update_forward_refs()
KLEUpdateInput.update_forward_refs()
LeaveCreateInput.update_forward_refs()
LeaveFilter.update_forward_refs()
LeaveRegistrationFilter.update_forward_refs()
LeaveTerminateInput.update_forward_refs()
LeaveUpdateInput.update_forward_refs()
ManagerCreateInput.update_forward_refs()
ManagerFilter.update_forward_refs()
ManagerRegistrationFilter.update_forward_refs()
ManagerTerminateInput.update_forward_refs()
ManagerUpdateInput.update_forward_refs()
ModelsUuidsBoundRegistrationFilter.update_forward_refs()
OrgUnitsboundaddressfilter.update_forward_refs()
OrgUnitsboundassociationfilter.update_forward_refs()
OrgUnitsboundengagementfilter.update_forward_refs()
OrgUnitsboundituserfilter.update_forward_refs()
OrgUnitsboundklefilter.update_forward_refs()
OrgUnitsboundleavefilter.update_forward_refs()
OrgUnitsboundmanagerfilter.update_forward_refs()
OrgUnitsboundrelatedunitfilter.update_forward_refs()
OrganisationCreate.update_forward_refs()
OrganisationUnitCreateInput.update_forward_refs()
OrganisationUnitFilter.update_forward_refs()
OrganisationUnitRegistrationFilter.update_forward_refs()
OrganisationUnitTerminateInput.update_forward_refs()
OrganisationUnitUpdateInput.update_forward_refs()
OwnerCreateInput.update_forward_refs()
OwnerFilter.update_forward_refs()
OwnerTerminateInput.update_forward_refs()
OwnerUpdateInput.update_forward_refs()
ParentsBoundClassFilter.update_forward_refs()
ParentsBoundFacetFilter.update_forward_refs()
ParentsBoundOrganisationUnitFilter.update_forward_refs()
RAOpenValidityInput.update_forward_refs()
RAValidityInput.update_forward_refs()
RegistrationFilter.update_forward_refs()
RelatedUnitFilter.update_forward_refs()
RelatedUnitsUpdateInput.update_forward_refs()
RoleBindingCreateInput.update_forward_refs()
RoleBindingFilter.update_forward_refs()
RoleBindingTerminateInput.update_forward_refs()
RoleBindingUpdateInput.update_forward_refs()
RoleRegistrationFilter.update_forward_refs()
UuidsBoundClassFilter.update_forward_refs()
UuidsBoundEmployeeFilter.update_forward_refs()
UuidsBoundEngagementFilter.update_forward_refs()
UuidsBoundFacetFilter.update_forward_refs()
UuidsBoundITSystemFilter.update_forward_refs()
UuidsBoundITUserFilter.update_forward_refs()
UuidsBoundLeaveFilter.update_forward_refs()
UuidsBoundOrganisationUnitFilter.update_forward_refs()
ValidityInput.update_forward_refs()
