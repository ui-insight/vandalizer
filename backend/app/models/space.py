from typing import Optional

from beanie import Document


class Space(Document):
    uuid: str
    title: str
    user: str
    description: Optional[str] = None

    class Settings:
        name = "space"
