"""Native messaging relay for the Edge, Chrome and Firefox price extension."""

from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

EXTENSION_ORIGIN = "chrome-extension://egpckjdkngmjhlppongfolbhdceigiak/"
FIREFOX_EXTENSION_ID = "pricemonitor@price-monitor.local"
FIREFOX_MANIFEST_NAME = "com.pricemonitor.jd_edge.json"
MAX_INBOUND_BYTES = 3_000_000


def runtime_file() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA is missing")
    return Path(appdata) / "PriceMonitor" / "edge-bridge.json"


def relay(message: dict, forced_browser: str | None = None) -> dict:
    config = json.loads(runtime_file().read_text(encoding="utf-8"))
    browser = forced_browser or message.get("browser", "edge")
    if browser not in ("edge", "chrome", "firefox"):
        raise ValueError("Invalid capture browser")
    action = message.get("action")
    if action == "claim":
        path = "/api/v1/edge/claim"
        payload: dict = {
            "browser": browser,
            "capabilities": message.get("capabilities", ["jd"]),
            "protocol_version": message.get("protocol_version", 1),
        }
    elif action == "result":
        request_id = message.get("id", "")
        if not isinstance(request_id, str) or len(request_id) != 32 or not request_id.isalnum():
            raise ValueError("Invalid request ID")
        path = f"/api/v1/edge/result/{request_id}"
        payload = message.get("observation", {})
        if not isinstance(payload, dict):
            raise ValueError("Invalid observation")
        payload = {**payload, "browser": browser}
    else:
        raise ValueError("Unknown bridge action")

    port = int(config["port"])
    token = str(config["token"])
    if not (1 <= port <= 65535) or len(token) != 64:
        raise ValueError("Invalid bridge configuration")
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def authorized_caller(args: list[str], executable: Path | None = None) -> bool:
    if args and args[0].rstrip("/") == EXTENSION_ORIGIN.rstrip("/"):
        return True
    if len(args) < 2 or args[1] != FIREFOX_EXTENSION_ID:
        return False
    expected = ((executable or Path(sys.executable)).resolve().parent / FIREFOX_MANIFEST_NAME)
    return Path(args[0]).resolve() == expected.resolve()


def main(args: list[str]) -> int:
    if not authorized_caller(args):
        return 2
    forced_browser = "firefox" if args[0].endswith(FIREFOX_MANIFEST_NAME) else None
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    if os.name == "nt":
        import msvcrt

        msvcrt.setmode(stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(stdout.fileno(), os.O_BINARY)
    while True:
        header = stdin.read(4)
        if not header:
            return 0
        if len(header) != 4:
            return 1
        size = struct.unpack("=I", header)[0]
        if size > MAX_INBOUND_BYTES:
            return 1
        data = stdin.read(size)
        if len(data) != size:
            return 1
        try:
            response = relay(json.loads(data), forced_browser)
        except (OSError, ValueError, KeyError, URLError) as exc:
            response = {"error": str(exc)[:200]}
        output = json.dumps(response, ensure_ascii=False).encode("utf-8")
        stdout.write(struct.pack("=I", len(output)))
        stdout.write(output)
        stdout.flush()
