from __future__ import annotations

from pydantic import BaseModel


class Lead(BaseModel):
    """A lead sourced from Specter."""

    specter_id: str
    first_name: str
    last_name: str
    email: str
    company: str
    title: str | None = None
    linkedin_url: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
