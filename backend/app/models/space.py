from typing import Optional

from beanie import Document


class Space(Document):
    uuid: str
    title: str
    user: Optional[str] = None

    class Settings:
        name = "space"
