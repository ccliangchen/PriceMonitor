from dataclasses import dataclass
from typing import Protocol


@dataclass
class NotificationMessage:
    title: str
    body: str
    url: str | None = None


class Notifier(Protocol):
    channel: str

    async def send(self, message: NotificationMessage) -> None: ...
