from typing import Annotated
from .config import Settings as Settings_
from fastapi import Depends
from .dataloaders import DataLoader as DataLoader_
from .import_export import SyncTool as SyncTool_
from ldap3 import Connection
from .converters import LdapConverter
from fastramqpi.depends import from_user_context

Settings = Annotated[Settings_, Depends(from_user_context("settings"))]
DataLoader = Annotated[DataLoader_, Depends(from_user_context("dataloader"))]

SyncTool = Annotated[SyncTool_, Depends(from_user_context("sync_tool"))]
LdapConnection = Annotated[Connection, Depends(from_user_context("ldap_connection"))]
LdapConverter = Annotated[Connection, Depends(from_user_context("ldap_connection"))]