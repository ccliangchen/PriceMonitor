from __future__ import annotations

import httpx

from app.notifiers.base import NotificationMessage, Notifier

SERVERCHAN_URL = "https://sctapi.ftqq.com/{sendkey}.send"


class ServerChanNotifier(Notifier):
    channel = "serverchan"

    def __init__(self, sendkey: str, timeout: float = 15.0) -> None:
        self.sendkey = sendkey
        self.timeout = timeout

    async def send(self, message: NotificationMessage) -> None:
        url = SERVERCHAN_URL.format(sendkey=self.sendkey)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                data={"title": message.title, "desp": message.body},
            )
            response.raise_for_status()
            payload = response.json()

        if payload.get("code") != 0:
            raise RuntimeError(f"ServerChan returned an error: {payload}")
        data = payload.get("data") or {}
        if data.get("error"):
            raise RuntimeError(f"ServerChan push error: {data['error']}")
