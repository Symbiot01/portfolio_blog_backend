"""Access token generator."""

from __future__ import annotations

from uuid import UUID, uuid4


class UuidTokenGen:
    def new(self) -> UUID:
        return uuid4()
