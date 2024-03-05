from typing import List
from typing import Optional

from .base_model import BaseModel


class ReadItsystemUserKey(BaseModel):
    itsystems: "ReadItsystemUserKeyItsystems"


class ReadItsystemUserKeyItsystems(BaseModel):
    objects: List["ReadItsystemUserKeyItsystemsObjects"]


class ReadItsystemUserKeyItsystemsObjects(BaseModel):
    current: Optional["ReadItsystemUserKeyItsystemsObjectsCurrent"]


class ReadItsystemUserKeyItsystemsObjectsCurrent(BaseModel):
    user_key: str


ReadItsystemUserKey.update_forward_refs()
ReadItsystemUserKeyItsystems.update_forward_refs()
ReadItsystemUserKeyItsystemsObjects.update_forward_refs()
ReadItsystemUserKeyItsystemsObjectsCurrent.update_forward_refs()
