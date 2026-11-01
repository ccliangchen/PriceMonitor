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

        code = payload.get("code")
        if str(code) != "0":
            raise RuntimeError(f"ServerChan 返回错误：{payload}")
        data = payload.get("data")
        if not isinstance(data, dict):
            data = {}
        # ServerChan returns ``data.error == "SUCCESS"`` after a successful
        # push. Treating that truthy value as a failure makes the UI report
        # an error even though WeChat already received the message.
        error = str(data.get("error") or "").strip()
        if error and error.upper() not in ("SUCCESS", "OK"):
            raise RuntimeError(f"ServerChan 推送失败：{error}")
