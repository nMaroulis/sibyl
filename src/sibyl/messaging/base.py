"""Small transport contract; channels own their native API details."""

from abc import ABC, abstractmethod


class MessagingClient(ABC):
    """Authenticate, receive and reply without owning an AI agent."""

    @abstractmethod
    async def identity(self) -> dict:
        """Return the authenticated bot identity and validate its receive transport."""

    @abstractmethod
    async def receive(self, offset: int | None) -> list[dict]:
        """Read a bounded native update page, without acknowledging it locally."""

    @abstractmethod
    async def send(self, chat_id: int, text: str) -> int:
        """Deliver plain text to one authorized chat and return its native message ID."""
