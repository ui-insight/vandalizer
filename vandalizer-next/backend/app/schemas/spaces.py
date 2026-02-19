from typing import Optional
from pydantic import BaseModel


class CreateSpaceRequest(BaseModel):
    title: str


class SpaceResponse(BaseModel):
    id: str
    uuid: str
    title: str
    user: Optional[str] = None
