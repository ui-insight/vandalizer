import datetime
from typing import Optional

from beanie import Document
from pydantic import Field
from beanie import PydanticObjectId


class User(Document):
    user_id: str
    email: Optional[str] = None
    is_admin: bool = False
    is_examiner: bool = False
    name: Optional[str] = None
    current_team: Optional[PydanticObjectId] = None
    api_token: Optional[str] = None
    api_token_created_at: Optional[datetime.datetime] = None
    api_token_expires_at: Optional[datetime.datetime] = None
    browser_automation_session_id: Optional[str] = None
    m365_enabled: bool = False
    m365_connected_at: Optional[datetime.datetime] = None
    password_hash: Optional[str] = None
    is_demo_user: bool = False
    demo_expires_at: Optional[datetime.datetime] = None
    demo_status: Optional[str] = None  # active | expired | locked
    organization_id: Optional[str] = None  # org uuid for university hierarchy

    class Settings:
        name = "user"
        indexes = [
            "user_id",
            "email",
            "api_token",
        ]
