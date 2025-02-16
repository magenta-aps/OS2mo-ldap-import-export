from ._testing__address_read import TestingAddressRead
from ._testing__address_read import TestingAddressReadAddresses
from ._testing__address_read import TestingAddressReadAddressesObjects
from ._testing__address_read import TestingAddressReadAddressesObjectsValidities
from ._testing__address_read import (
    TestingAddressReadAddressesObjectsValiditiesAddressType,
)
from ._testing__address_read import TestingAddressReadAddressesObjectsValiditiesPerson
from ._testing__address_read import TestingAddressReadAddressesObjectsValiditiesValidity
from ._testing__address_read import (
    TestingAddressReadAddressesObjectsValiditiesVisibility,
)
from ._testing__employee_read import TestingEmployeeRead
from ._testing__employee_read import TestingEmployeeReadEmployees
from ._testing__employee_read import TestingEmployeeReadEmployeesObjects
from ._testing__employee_read import TestingEmployeeReadEmployeesObjectsValidities
from ._testing__engagement_read import TestingEngagementRead
from ._testing__engagement_read import TestingEngagementReadEngagements
from ._testing__engagement_read import TestingEngagementReadEngagementsObjects
from ._testing__engagement_read import TestingEngagementReadEngagementsObjectsValidities
from ._testing__engagement_read import (
    TestingEngagementReadEngagementsObjectsValiditiesEngagementType,
)
from ._testing__engagement_read import (
    TestingEngagementReadEngagementsObjectsValiditiesJobFunction,
)
from ._testing__engagement_read import (
    TestingEngagementReadEngagementsObjectsValiditiesOrgUnit,
)
from ._testing__engagement_read import (
    TestingEngagementReadEngagementsObjectsValiditiesPerson,
)
from ._testing__engagement_read import (
    TestingEngagementReadEngagementsObjectsValiditiesPrimary,
)
from ._testing__engagement_read import (
    TestingEngagementReadEngagementsObjectsValiditiesValidity,
)
from ._testing__itsystem_create import TestingItsystemCreate
from ._testing__itsystem_create import TestingItsystemCreateItsystemCreate
from ._testing__ituser_read import TestingItuserRead
from ._testing__ituser_read import TestingItuserReadItusers
from ._testing__ituser_read import TestingItuserReadItusersObjects
from ._testing__ituser_read import TestingItuserReadItusersObjectsValidities
from ._testing__ituser_read import TestingItuserReadItusersObjectsValiditiesItsystem
from ._testing__ituser_read import TestingItuserReadItusersObjectsValiditiesPerson
from ._testing__ituser_read import TestingItuserReadItusersObjectsValiditiesValidity
from .address_create import AddressCreate
from .address_create import AddressCreateAddressCreate
from .address_terminate import AddressTerminate
from .address_terminate import AddressTerminateAddressTerminate
from .address_update import AddressUpdate
from .address_update import AddressUpdateAddressUpdate
from .async_base_client import AsyncBaseClient
from .base_model import BaseModel
from .class_create import ClassCreate
from .class_create import ClassCreateClassCreate
from .client import GraphQLClient
from .employee_refresh import EmployeeRefresh
from .employee_refresh import EmployeeRefreshEmployeeRefresh
from .engagement_create import EngagementCreate
from .engagement_create import EngagementCreateEngagementCreate
from .engagement_terminate import EngagementTerminate
from .engagement_terminate import EngagementTerminateEngagementTerminate
from .engagement_update import EngagementUpdate
from .engagement_update import EngagementUpdateEngagementUpdate
from .enums import AuditLogModel
from .enums import FileStore
from .enums import OwnerInferencePriority
from .exceptions import GraphQLClientError
from .exceptions import GraphQLClientGraphQLError
from .exceptions import GraphQLClientGraphQLMultiError
from .exceptions import GraphQLClientHttpError
from .exceptions import GraphQlClientInvalidResponseError
from .input_types import AddressCreateInput
from .input_types import AddressFilter
from .input_types import AddressRegistrationFilter
from .input_types import AddressTerminateInput
from .input_types import AddressUpdateInput
from .input_types import AssociationCreateInput
from .input_types import AssociationFilter
from .input_types import AssociationRegistrationFilter
from .input_types import AssociationTerminateInput
from .input_types import AssociationUpdateInput
from .input_types import AuditLogFilter
from .input_types import ClassCreateInput
from .input_types import ClassFilter
from .input_types import ClassOwnerFilter
from .input_types import ClassRegistrationFilter
from .input_types import ClassTerminateInput
from .input_types import ClassUpdateInput
from .input_types import ConfigurationFilter
from .input_types import EmployeeCreateInput
from .input_types import EmployeeFilter
from .input_types import EmployeeRegistrationFilter
from .input_types import EmployeesBoundAddressFilter
from .input_types import EmployeesBoundAssociationFilter
from .input_types import EmployeesBoundEngagementFilter
from .input_types import EmployeesBoundITUserFilter
from .input_types import EmployeesBoundLeaveFilter
from .input_types import EmployeesBoundManagerFilter
from .input_types import EmployeeTerminateInput
from .input_types import EmployeeUpdateInput
from .input_types import EngagementCreateInput
from .input_types import EngagementFilter
from .input_types import EngagementRegistrationFilter
from .input_types import EngagementTerminateInput
from .input_types import EngagementUpdateInput
from .input_types import FacetCreateInput
from .input_types import FacetFilter
from .input_types import FacetRegistrationFilter
from .input_types import FacetsBoundClassFilter
from .input_types import FacetTerminateInput
from .input_types import FacetUpdateInput
from .input_types import FileFilter
from .input_types import HealthFilter
from .input_types import ITAssociationCreateInput
from .input_types import ITAssociationTerminateInput
from .input_types import ITAssociationUpdateInput
from .input_types import ITSystemCreateInput
from .input_types import ITSystemFilter
from .input_types import ITSystemRegistrationFilter
from .input_types import ITSystemTerminateInput
from .input_types import ITSystemUpdateInput
from .input_types import ItuserBoundAddressFilter
from .input_types import ItuserBoundRoleBindingFilter
from .input_types import ITUserCreateInput
from .input_types import ITUserFilter
from .input_types import ITUserRegistrationFilter
from .input_types import ITUserTerminateInput
from .input_types import ITUserUpdateInput
from .input_types import KLECreateInput
from .input_types import KLEFilter
from .input_types import KLERegistrationFilter
from .input_types import KLETerminateInput
from .input_types import KLEUpdateInput
from .input_types import LeaveCreateInput
from .input_types import LeaveFilter
from .input_types import LeaveRegistrationFilter
from .input_types import LeaveTerminateInput
from .input_types import LeaveUpdateInput
from .input_types import ManagerCreateInput
from .input_types import ManagerFilter
from .input_types import ManagerRegistrationFilter
from .input_types import ManagerTerminateInput
from .input_types import ManagerUpdateInput
from .input_types import ModelsUuidsBoundRegistrationFilter
from .input_types import OrganisationCreate
from .input_types import OrganisationUnitCreateInput
from .input_types import OrganisationUnitFilter
from .input_types import OrganisationUnitRegistrationFilter
from .input_types import OrganisationUnitTerminateInput
from .input_types import OrganisationUnitUpdateInput
from .input_types import OrgUnitsboundaddressfilter
from .input_types import OrgUnitsboundassociationfilter
from .input_types import OrgUnitsboundengagementfilter
from .input_types import OrgUnitsboundituserfilter
from .input_types import OrgUnitsboundklefilter
from .input_types import OrgUnitsboundleavefilter
from .input_types import OrgUnitsboundrelatedunitfilter
from .input_types import OwnerCreateInput
from .input_types import OwnerFilter
from .input_types import OwnerTerminateInput
from .input_types import OwnerUpdateInput
from .input_types import ParentsBoundClassFilter
from .input_types import ParentsBoundFacetFilter
from .input_types import ParentsBoundOrganisationUnitFilter
from .input_types import RAOpenValidityInput
from .input_types import RAValidityInput
from .input_types import RegistrationFilter
from .input_types import RelatedUnitFilter
from .input_types import RelatedUnitsUpdateInput
from .input_types import RoleBindingCreateInput
from .input_types import RoleBindingFilter
from .input_types import RoleBindingTerminateInput
from .input_types import RoleBindingUpdateInput
from .input_types import RoleRegistrationFilter
from .input_types import UuidsBoundClassFilter
from .input_types import UuidsBoundEmployeeFilter
from .input_types import UuidsBoundEngagementFilter
from .input_types import UuidsBoundFacetFilter
from .input_types import UuidsBoundITSystemFilter
from .input_types import UuidsBoundITUserFilter
from .input_types import UuidsBoundLeaveFilter
from .input_types import UuidsBoundOrganisationUnitFilter
from .input_types import ValidityInput
from .ituser_create import ItuserCreate
from .ituser_create import ItuserCreateItuserCreate
from .ituser_terminate import ItuserTerminate
from .ituser_terminate import ItuserTerminateItuserTerminate
from .ituser_update import ItuserUpdate
from .ituser_update import ItuserUpdateItuserUpdate
from .org_unit_create import OrgUnitCreate
from .org_unit_create import OrgUnitCreateOrgUnitCreate
from .org_unit_engagements_refresh import OrgUnitEngagementsRefresh
from .org_unit_engagements_refresh import OrgUnitEngagementsRefreshEngagementRefresh
from .read_address_relation_uuids import ReadAddressRelationUuids
from .read_address_relation_uuids import ReadAddressRelationUuidsAddresses
from .read_address_relation_uuids import ReadAddressRelationUuidsAddressesObjects
from .read_address_relation_uuids import ReadAddressRelationUuidsAddressesObjectsCurrent
from .read_address_uuid import ReadAddressUuid
from .read_address_uuid import ReadAddressUuidAddresses
from .read_address_uuid import ReadAddressUuidAddressesObjects
from .read_addresses import ReadAddresses
from .read_addresses import ReadAddressesAddresses
from .read_addresses import ReadAddressesAddressesObjects
from .read_addresses import ReadAddressesAddressesObjectsValidities
from .read_addresses import ReadAddressesAddressesObjectsValiditiesAddressType
from .read_addresses import ReadAddressesAddressesObjectsValiditiesPerson
from .read_addresses import ReadAddressesAddressesObjectsValiditiesValidity
from .read_all_ituser_user_keys_by_itsystem_uuid import (
    ReadAllItuserUserKeysByItsystemUuid,
)
from .read_all_ituser_user_keys_by_itsystem_uuid import (
    ReadAllItuserUserKeysByItsystemUuidItusers,
)
from .read_all_ituser_user_keys_by_itsystem_uuid import (
    ReadAllItuserUserKeysByItsystemUuidItusersObjects,
)
from .read_all_ituser_user_keys_by_itsystem_uuid import (
    ReadAllItuserUserKeysByItsystemUuidItusersObjectsValidities,
)
from .read_all_itusers import ReadAllItusers
from .read_all_itusers import ReadAllItusersItusers
from .read_all_itusers import ReadAllItusersItusersObjects
from .read_all_itusers import ReadAllItusersItusersObjectsValidities
from .read_all_itusers import ReadAllItusersItusersPageInfo
from .read_class_name_by_class_uuid import ReadClassNameByClassUuid
from .read_class_name_by_class_uuid import ReadClassNameByClassUuidClasses
from .read_class_name_by_class_uuid import ReadClassNameByClassUuidClassesObjects
from .read_class_name_by_class_uuid import ReadClassNameByClassUuidClassesObjectsCurrent
from .read_class_uuid import ReadClassUuid
from .read_class_uuid import ReadClassUuidClasses
from .read_class_uuid import ReadClassUuidClassesObjects
from .read_class_uuid_by_facet_and_class_user_key import (
    ReadClassUuidByFacetAndClassUserKey,
)
from .read_class_uuid_by_facet_and_class_user_key import (
    ReadClassUuidByFacetAndClassUserKeyClasses,
)
from .read_class_uuid_by_facet_and_class_user_key import (
    ReadClassUuidByFacetAndClassUserKeyClassesObjects,
)
from .read_employee_uuid_by_cpr_number import ReadEmployeeUuidByCprNumber
from .read_employee_uuid_by_cpr_number import ReadEmployeeUuidByCprNumberEmployees
from .read_employee_uuid_by_cpr_number import (
    ReadEmployeeUuidByCprNumberEmployeesObjects,
)
from .read_employee_uuid_by_ituser_user_key import ReadEmployeeUuidByItuserUserKey
from .read_employee_uuid_by_ituser_user_key import (
    ReadEmployeeUuidByItuserUserKeyItusers,
)
from .read_employee_uuid_by_ituser_user_key import (
    ReadEmployeeUuidByItuserUserKeyItusersObjects,
)
from .read_employee_uuid_by_ituser_user_key import (
    ReadEmployeeUuidByItuserUserKeyItusersObjectsCurrent,
)
from .read_employees import ReadEmployees
from .read_employees import ReadEmployeesEmployees
from .read_employees import ReadEmployeesEmployeesObjects
from .read_employees import ReadEmployeesEmployeesObjectsValidities
from .read_employees import ReadEmployeesEmployeesObjectsValiditiesValidity
from .read_employees_with_engagement_to_org_unit import (
    ReadEmployeesWithEngagementToOrgUnit,
)
from .read_employees_with_engagement_to_org_unit import (
    ReadEmployeesWithEngagementToOrgUnitEngagements,
)
from .read_employees_with_engagement_to_org_unit import (
    ReadEmployeesWithEngagementToOrgUnitEngagementsObjects,
)
from .read_employees_with_engagement_to_org_unit import (
    ReadEmployeesWithEngagementToOrgUnitEngagementsObjectsCurrent,
)
from .read_engagement_employee_uuid import ReadEngagementEmployeeUuid
from .read_engagement_employee_uuid import ReadEngagementEmployeeUuidEngagements
from .read_engagement_employee_uuid import ReadEngagementEmployeeUuidEngagementsObjects
from .read_engagement_employee_uuid import (
    ReadEngagementEmployeeUuidEngagementsObjectsCurrent,
)
from .read_engagement_enddate import ReadEngagementEnddate
from .read_engagement_enddate import ReadEngagementEnddateEngagements
from .read_engagement_enddate import ReadEngagementEnddateEngagementsObjects
from .read_engagement_enddate import ReadEngagementEnddateEngagementsObjectsValidities
from .read_engagement_enddate import (
    ReadEngagementEnddateEngagementsObjectsValiditiesValidity,
)
from .read_engagement_uuid import ReadEngagementUuid
from .read_engagement_uuid import ReadEngagementUuidEngagements
from .read_engagement_uuid import ReadEngagementUuidEngagementsObjects
from .read_engagements import ReadEngagements
from .read_engagements import ReadEngagementsEngagements
from .read_engagements import ReadEngagementsEngagementsObjects
from .read_engagements import ReadEngagementsEngagementsObjectsValidities
from .read_engagements import ReadEngagementsEngagementsObjectsValiditiesValidity
from .read_engagements_by_employee_uuid import ReadEngagementsByEmployeeUuid
from .read_engagements_by_employee_uuid import ReadEngagementsByEmployeeUuidEngagements
from .read_engagements_by_employee_uuid import (
    ReadEngagementsByEmployeeUuidEngagementsObjects,
)
from .read_engagements_by_employee_uuid import (
    ReadEngagementsByEmployeeUuidEngagementsObjectsCurrent,
)
from .read_engagements_by_employee_uuid import (
    ReadEngagementsByEmployeeUuidEngagementsObjectsCurrentValidity,
)
from .read_engagements_is_primary import ReadEngagementsIsPrimary
from .read_engagements_is_primary import ReadEngagementsIsPrimaryEngagements
from .read_engagements_is_primary import ReadEngagementsIsPrimaryEngagementsObjects
from .read_engagements_is_primary import (
    ReadEngagementsIsPrimaryEngagementsObjectsValidities,
)
from .read_engagements_is_primary import (
    ReadEngagementsIsPrimaryEngagementsObjectsValiditiesValidity,
)
from .read_facet_uuid import ReadFacetUuid
from .read_facet_uuid import ReadFacetUuidFacets
from .read_facet_uuid import ReadFacetUuidFacetsObjects
from .read_filtered_addresses import ReadFilteredAddresses
from .read_filtered_addresses import ReadFilteredAddressesAddresses
from .read_filtered_addresses import ReadFilteredAddressesAddressesObjects
from .read_filtered_addresses import ReadFilteredAddressesAddressesObjectsValidities
from .read_filtered_addresses import (
    ReadFilteredAddressesAddressesObjectsValiditiesAddressType,
)
from .read_filtered_addresses import (
    ReadFilteredAddressesAddressesObjectsValiditiesValidity,
)
from .read_filtered_itusers import ReadFilteredItusers
from .read_filtered_itusers import ReadFilteredItusersItusers
from .read_filtered_itusers import ReadFilteredItusersItusersObjects
from .read_filtered_itusers import ReadFilteredItusersItusersObjectsValidities
from .read_filtered_itusers import ReadFilteredItusersItusersObjectsValiditiesItsystem
from .read_filtered_itusers import ReadFilteredItusersItusersObjectsValiditiesValidity
from .read_itsystem_uuid import ReadItsystemUuid
from .read_itsystem_uuid import ReadItsystemUuidItsystems
from .read_itsystem_uuid import ReadItsystemUuidItsystemsObjects
from .read_ituser_by_employee_and_itsystem_uuid import (
    ReadItuserByEmployeeAndItsystemUuid,
)
from .read_ituser_by_employee_and_itsystem_uuid import (
    ReadItuserByEmployeeAndItsystemUuidItusers,
)
from .read_ituser_by_employee_and_itsystem_uuid import (
    ReadItuserByEmployeeAndItsystemUuidItusersObjects,
)
from .read_ituser_employee_uuid import ReadItuserEmployeeUuid
from .read_ituser_employee_uuid import ReadItuserEmployeeUuidItusers
from .read_ituser_employee_uuid import ReadItuserEmployeeUuidItusersObjects
from .read_ituser_employee_uuid import ReadItuserEmployeeUuidItusersObjectsCurrent
from .read_ituser_uuid import ReadItuserUuid
from .read_ituser_uuid import ReadItuserUuidItusers
from .read_ituser_uuid import ReadItuserUuidItusersObjects
from .read_itusers import ReadItusers
from .read_itusers import ReadItusersItusers
from .read_itusers import ReadItusersItusersObjects
from .read_itusers import ReadItusersItusersObjectsValidities
from .read_itusers import ReadItusersItusersObjectsValiditiesValidity
from .read_org_unit_ancestor_names import ReadOrgUnitAncestorNames
from .read_org_unit_ancestor_names import ReadOrgUnitAncestorNamesOrgUnits
from .read_org_unit_ancestor_names import ReadOrgUnitAncestorNamesOrgUnitsObjects
from .read_org_unit_ancestor_names import ReadOrgUnitAncestorNamesOrgUnitsObjectsCurrent
from .read_org_unit_ancestor_names import (
    ReadOrgUnitAncestorNamesOrgUnitsObjectsCurrentAncestors,
)
from .read_org_unit_ancestors import ReadOrgUnitAncestors
from .read_org_unit_ancestors import ReadOrgUnitAncestorsOrgUnits
from .read_org_unit_ancestors import ReadOrgUnitAncestorsOrgUnitsObjects
from .read_org_unit_ancestors import ReadOrgUnitAncestorsOrgUnitsObjectsCurrent
from .read_org_unit_ancestors import ReadOrgUnitAncestorsOrgUnitsObjectsCurrentAncestors
from .read_org_unit_name import ReadOrgUnitName
from .read_org_unit_name import ReadOrgUnitNameOrgUnits
from .read_org_unit_name import ReadOrgUnitNameOrgUnitsObjects
from .read_org_unit_name import ReadOrgUnitNameOrgUnitsObjectsCurrent
from .read_person_uuid import ReadPersonUuid
from .read_person_uuid import ReadPersonUuidEmployees
from .read_person_uuid import ReadPersonUuidEmployeesObjects
from .set_job_title import SetJobTitle
from .set_job_title import SetJobTitleEngagementUpdate
from .user_create import UserCreate
from .user_create import UserCreateEmployeeCreate
from .user_update import UserUpdate
from .user_update import UserUpdateEmployeeUpdate

__all__ = [
    "AddressCreate",
    "AddressCreateAddressCreate",
    "AddressCreateInput",
    "AddressFilter",
    "AddressRegistrationFilter",
    "AddressTerminate",
    "AddressTerminateAddressTerminate",
    "AddressTerminateInput",
    "AddressUpdate",
    "AddressUpdateAddressUpdate",
    "AddressUpdateInput",
    "AssociationCreateInput",
    "AssociationFilter",
    "AssociationRegistrationFilter",
    "AssociationTerminateInput",
    "AssociationUpdateInput",
    "AsyncBaseClient",
    "AuditLogFilter",
    "AuditLogModel",
    "BaseModel",
    "ClassCreate",
    "ClassCreateClassCreate",
    "ClassCreateInput",
    "ClassFilter",
    "ClassOwnerFilter",
    "ClassRegistrationFilter",
    "ClassTerminateInput",
    "ClassUpdateInput",
    "ConfigurationFilter",
    "EmployeeCreateInput",
    "EmployeeFilter",
    "EmployeeRefresh",
    "EmployeeRefreshEmployeeRefresh",
    "EmployeeRegistrationFilter",
    "EmployeeTerminateInput",
    "EmployeeUpdateInput",
    "EmployeesBoundAddressFilter",
    "EmployeesBoundAssociationFilter",
    "EmployeesBoundEngagementFilter",
    "EmployeesBoundITUserFilter",
    "EmployeesBoundLeaveFilter",
    "EmployeesBoundManagerFilter",
    "EngagementCreate",
    "EngagementCreateEngagementCreate",
    "EngagementCreateInput",
    "EngagementFilter",
    "EngagementRegistrationFilter",
    "EngagementTerminate",
    "EngagementTerminateEngagementTerminate",
    "EngagementTerminateInput",
    "EngagementUpdate",
    "EngagementUpdateEngagementUpdate",
    "EngagementUpdateInput",
    "FacetCreateInput",
    "FacetFilter",
    "FacetRegistrationFilter",
    "FacetTerminateInput",
    "FacetUpdateInput",
    "FacetsBoundClassFilter",
    "FileFilter",
    "FileStore",
    "GraphQLClient",
    "GraphQLClientError",
    "GraphQLClientGraphQLError",
    "GraphQLClientGraphQLMultiError",
    "GraphQLClientHttpError",
    "GraphQlClientInvalidResponseError",
    "HealthFilter",
    "ITAssociationCreateInput",
    "ITAssociationTerminateInput",
    "ITAssociationUpdateInput",
    "ITSystemCreateInput",
    "ITSystemFilter",
    "ITSystemRegistrationFilter",
    "ITSystemTerminateInput",
    "ITSystemUpdateInput",
    "ITUserCreateInput",
    "ITUserFilter",
    "ITUserRegistrationFilter",
    "ITUserTerminateInput",
    "ITUserUpdateInput",
    "ItuserBoundAddressFilter",
    "ItuserBoundRoleBindingFilter",
    "ItuserCreate",
    "ItuserCreateItuserCreate",
    "ItuserTerminate",
    "ItuserTerminateItuserTerminate",
    "ItuserUpdate",
    "ItuserUpdateItuserUpdate",
    "KLECreateInput",
    "KLEFilter",
    "KLERegistrationFilter",
    "KLETerminateInput",
    "KLEUpdateInput",
    "LeaveCreateInput",
    "LeaveFilter",
    "LeaveRegistrationFilter",
    "LeaveTerminateInput",
    "LeaveUpdateInput",
    "ManagerCreateInput",
    "ManagerFilter",
    "ManagerRegistrationFilter",
    "ManagerTerminateInput",
    "ManagerUpdateInput",
    "ModelsUuidsBoundRegistrationFilter",
    "OrgUnitCreate",
    "OrgUnitCreateOrgUnitCreate",
    "OrgUnitEngagementsRefresh",
    "OrgUnitEngagementsRefreshEngagementRefresh",
    "OrgUnitsboundaddressfilter",
    "OrgUnitsboundassociationfilter",
    "OrgUnitsboundengagementfilter",
    "OrgUnitsboundituserfilter",
    "OrgUnitsboundklefilter",
    "OrgUnitsboundleavefilter",
    "OrgUnitsboundrelatedunitfilter",
    "OrganisationCreate",
    "OrganisationUnitCreateInput",
    "OrganisationUnitFilter",
    "OrganisationUnitRegistrationFilter",
    "OrganisationUnitTerminateInput",
    "OrganisationUnitUpdateInput",
    "OwnerCreateInput",
    "OwnerFilter",
    "OwnerInferencePriority",
    "OwnerTerminateInput",
    "OwnerUpdateInput",
    "ParentsBoundClassFilter",
    "ParentsBoundFacetFilter",
    "ParentsBoundOrganisationUnitFilter",
    "RAOpenValidityInput",
    "RAValidityInput",
    "ReadAddressRelationUuids",
    "ReadAddressRelationUuidsAddresses",
    "ReadAddressRelationUuidsAddressesObjects",
    "ReadAddressRelationUuidsAddressesObjectsCurrent",
    "ReadAddressUuid",
    "ReadAddressUuidAddresses",
    "ReadAddressUuidAddressesObjects",
    "ReadAddresses",
    "ReadAddressesAddresses",
    "ReadAddressesAddressesObjects",
    "ReadAddressesAddressesObjectsValidities",
    "ReadAddressesAddressesObjectsValiditiesAddressType",
    "ReadAddressesAddressesObjectsValiditiesPerson",
    "ReadAddressesAddressesObjectsValiditiesValidity",
    "ReadAllItuserUserKeysByItsystemUuid",
    "ReadAllItuserUserKeysByItsystemUuidItusers",
    "ReadAllItuserUserKeysByItsystemUuidItusersObjects",
    "ReadAllItuserUserKeysByItsystemUuidItusersObjectsValidities",
    "ReadAllItusers",
    "ReadAllItusersItusers",
    "ReadAllItusersItusersObjects",
    "ReadAllItusersItusersObjectsValidities",
    "ReadAllItusersItusersPageInfo",
    "ReadClassNameByClassUuid",
    "ReadClassNameByClassUuidClasses",
    "ReadClassNameByClassUuidClassesObjects",
    "ReadClassNameByClassUuidClassesObjectsCurrent",
    "ReadClassUuid",
    "ReadClassUuidByFacetAndClassUserKey",
    "ReadClassUuidByFacetAndClassUserKeyClasses",
    "ReadClassUuidByFacetAndClassUserKeyClassesObjects",
    "ReadClassUuidClasses",
    "ReadClassUuidClassesObjects",
    "ReadEmployeeUuidByCprNumber",
    "ReadEmployeeUuidByCprNumberEmployees",
    "ReadEmployeeUuidByCprNumberEmployeesObjects",
    "ReadEmployeeUuidByItuserUserKey",
    "ReadEmployeeUuidByItuserUserKeyItusers",
    "ReadEmployeeUuidByItuserUserKeyItusersObjects",
    "ReadEmployeeUuidByItuserUserKeyItusersObjectsCurrent",
    "ReadEmployees",
    "ReadEmployeesEmployees",
    "ReadEmployeesEmployeesObjects",
    "ReadEmployeesEmployeesObjectsValidities",
    "ReadEmployeesEmployeesObjectsValiditiesValidity",
    "ReadEmployeesWithEngagementToOrgUnit",
    "ReadEmployeesWithEngagementToOrgUnitEngagements",
    "ReadEmployeesWithEngagementToOrgUnitEngagementsObjects",
    "ReadEmployeesWithEngagementToOrgUnitEngagementsObjectsCurrent",
    "ReadEngagementEmployeeUuid",
    "ReadEngagementEmployeeUuidEngagements",
    "ReadEngagementEmployeeUuidEngagementsObjects",
    "ReadEngagementEmployeeUuidEngagementsObjectsCurrent",
    "ReadEngagementEnddate",
    "ReadEngagementEnddateEngagements",
    "ReadEngagementEnddateEngagementsObjects",
    "ReadEngagementEnddateEngagementsObjectsValidities",
    "ReadEngagementEnddateEngagementsObjectsValiditiesValidity",
    "ReadEngagementUuid",
    "ReadEngagementUuidEngagements",
    "ReadEngagementUuidEngagementsObjects",
    "ReadEngagements",
    "ReadEngagementsByEmployeeUuid",
    "ReadEngagementsByEmployeeUuidEngagements",
    "ReadEngagementsByEmployeeUuidEngagementsObjects",
    "ReadEngagementsByEmployeeUuidEngagementsObjectsCurrent",
    "ReadEngagementsByEmployeeUuidEngagementsObjectsCurrentValidity",
    "ReadEngagementsEngagements",
    "ReadEngagementsEngagementsObjects",
    "ReadEngagementsEngagementsObjectsValidities",
    "ReadEngagementsEngagementsObjectsValiditiesValidity",
    "ReadEngagementsIsPrimary",
    "ReadEngagementsIsPrimaryEngagements",
    "ReadEngagementsIsPrimaryEngagementsObjects",
    "ReadEngagementsIsPrimaryEngagementsObjectsValidities",
    "ReadEngagementsIsPrimaryEngagementsObjectsValiditiesValidity",
    "ReadFacetUuid",
    "ReadFacetUuidFacets",
    "ReadFacetUuidFacetsObjects",
    "ReadFilteredAddresses",
    "ReadFilteredAddressesAddresses",
    "ReadFilteredAddressesAddressesObjects",
    "ReadFilteredAddressesAddressesObjectsValidities",
    "ReadFilteredAddressesAddressesObjectsValiditiesAddressType",
    "ReadFilteredAddressesAddressesObjectsValiditiesValidity",
    "ReadFilteredItusers",
    "ReadFilteredItusersItusers",
    "ReadFilteredItusersItusersObjects",
    "ReadFilteredItusersItusersObjectsValidities",
    "ReadFilteredItusersItusersObjectsValiditiesItsystem",
    "ReadFilteredItusersItusersObjectsValiditiesValidity",
    "ReadItsystemUuid",
    "ReadItsystemUuidItsystems",
    "ReadItsystemUuidItsystemsObjects",
    "ReadItuserByEmployeeAndItsystemUuid",
    "ReadItuserByEmployeeAndItsystemUuidItusers",
    "ReadItuserByEmployeeAndItsystemUuidItusersObjects",
    "ReadItuserEmployeeUuid",
    "ReadItuserEmployeeUuidItusers",
    "ReadItuserEmployeeUuidItusersObjects",
    "ReadItuserEmployeeUuidItusersObjectsCurrent",
    "ReadItuserUuid",
    "ReadItuserUuidItusers",
    "ReadItuserUuidItusersObjects",
    "ReadItusers",
    "ReadItusersItusers",
    "ReadItusersItusersObjects",
    "ReadItusersItusersObjectsValidities",
    "ReadItusersItusersObjectsValiditiesValidity",
    "ReadOrgUnitAncestorNames",
    "ReadOrgUnitAncestorNamesOrgUnits",
    "ReadOrgUnitAncestorNamesOrgUnitsObjects",
    "ReadOrgUnitAncestorNamesOrgUnitsObjectsCurrent",
    "ReadOrgUnitAncestorNamesOrgUnitsObjectsCurrentAncestors",
    "ReadOrgUnitAncestors",
    "ReadOrgUnitAncestorsOrgUnits",
    "ReadOrgUnitAncestorsOrgUnitsObjects",
    "ReadOrgUnitAncestorsOrgUnitsObjectsCurrent",
    "ReadOrgUnitAncestorsOrgUnitsObjectsCurrentAncestors",
    "ReadOrgUnitName",
    "ReadOrgUnitNameOrgUnits",
    "ReadOrgUnitNameOrgUnitsObjects",
    "ReadOrgUnitNameOrgUnitsObjectsCurrent",
    "ReadPersonUuid",
    "ReadPersonUuidEmployees",
    "ReadPersonUuidEmployeesObjects",
    "RegistrationFilter",
    "RelatedUnitFilter",
    "RelatedUnitsUpdateInput",
    "RoleBindingCreateInput",
    "RoleBindingFilter",
    "RoleBindingTerminateInput",
    "RoleBindingUpdateInput",
    "RoleRegistrationFilter",
    "SetJobTitle",
    "SetJobTitleEngagementUpdate",
    "TestingAddressRead",
    "TestingAddressReadAddresses",
    "TestingAddressReadAddressesObjects",
    "TestingAddressReadAddressesObjectsValidities",
    "TestingAddressReadAddressesObjectsValiditiesAddressType",
    "TestingAddressReadAddressesObjectsValiditiesPerson",
    "TestingAddressReadAddressesObjectsValiditiesValidity",
    "TestingAddressReadAddressesObjectsValiditiesVisibility",
    "TestingEmployeeRead",
    "TestingEmployeeReadEmployees",
    "TestingEmployeeReadEmployeesObjects",
    "TestingEmployeeReadEmployeesObjectsValidities",
    "TestingEngagementRead",
    "TestingEngagementReadEngagements",
    "TestingEngagementReadEngagementsObjects",
    "TestingEngagementReadEngagementsObjectsValidities",
    "TestingEngagementReadEngagementsObjectsValiditiesEngagementType",
    "TestingEngagementReadEngagementsObjectsValiditiesJobFunction",
    "TestingEngagementReadEngagementsObjectsValiditiesOrgUnit",
    "TestingEngagementReadEngagementsObjectsValiditiesPerson",
    "TestingEngagementReadEngagementsObjectsValiditiesPrimary",
    "TestingEngagementReadEngagementsObjectsValiditiesValidity",
    "TestingItsystemCreate",
    "TestingItsystemCreateItsystemCreate",
    "TestingItuserRead",
    "TestingItuserReadItusers",
    "TestingItuserReadItusersObjects",
    "TestingItuserReadItusersObjectsValidities",
    "TestingItuserReadItusersObjectsValiditiesItsystem",
    "TestingItuserReadItusersObjectsValiditiesPerson",
    "TestingItuserReadItusersObjectsValiditiesValidity",
    "UserCreate",
    "UserCreateEmployeeCreate",
    "UserUpdate",
    "UserUpdateEmployeeUpdate",
    "UuidsBoundClassFilter",
    "UuidsBoundEmployeeFilter",
    "UuidsBoundEngagementFilter",
    "UuidsBoundFacetFilter",
    "UuidsBoundITSystemFilter",
    "UuidsBoundITUserFilter",
    "UuidsBoundLeaveFilter",
    "UuidsBoundOrganisationUnitFilter",
    "ValidityInput",
]
