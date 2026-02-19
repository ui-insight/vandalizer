from typing import Optional

from beanie import Document


class SmartFolder(Document):
    parent_id: str
    title: str
    uuid: str
    space: str
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    is_shared_team_root: bool = False

    class Settings:
        name = "smart_folder"
