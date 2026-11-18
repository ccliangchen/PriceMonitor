import base64
import hashlib
import io
import json
from pathlib import Path

from app.native_host import (
    EXTENSION_ORIGIN,
    FIREFOX_EXTENSION_ID,
    authorized_caller,
)

ROOT = Path(__file__).resolve().parents[2]


def test_three_browser_native_host_manifests_share_extension_identity():
    extension = json.loads((ROOT / "extension/manifest.json").read_text(encoding="utf-8"))
    chromium = json.loads(
        (ROOT / "backend/packaging/edge-native-host.json").read_text(encoding="utf-8")
    )
    firefox = json.loads(
        (ROOT / "backend/packaging/com.pricemonitor.jd_edge.json").read_text(encoding="utf-8")
    )
    digest = hashlib.sha256(base64.b64decode(extension["key"])).hexdigest()[:32]
    chromium_id = "".join(chr(ord("a") + int(nibble, 16)) for nibble in digest)

    assert chromium_id == EXTENSION_ORIGIN.split("//", 1)[1].strip("/")
    assert chromium["allowed_origins"] == [EXTENSION_ORIGIN]
    assert firefox["allowed_extensions"] == [FIREFOX_EXTENSION_ID]
    assert f"{firefox['name']}.json" == "com.pricemonitor.jd_edge.json"
    assert extension["browser_specific_settings"]["gecko"]["id"] == FIREFOX_EXTENSION_ID
    assert chromium["name"] == firefox["name"]
    assert extension["background"]["service_worker"] == "background.js"
    assert extension["background"]["scripts"] == ["background.js"]


def test_native_host_rejects_other_browser_callers(tmp_path):
    executable = tmp_path / "price-monitor-backend.exe"
    firefox_manifest = tmp_path / "com.pricemonitor.jd_edge.json"

    assert authorized_caller([EXTENSION_ORIGIN, "--parent-window=0"], executable)
    assert authorized_caller([str(firefox_manifest), FIREFOX_EXTENSION_ID], executable)
    assert not authorized_caller(["chrome-extension://other-extension/"], executable)
    assert not authorized_caller([str(firefox_manifest), "other@example.org"], executable)
    assert not authorized_caller(
        [str(tmp_path / "other" / "com.pricemonitor.jd_edge.json"), FIREFOX_EXTENSION_ID],
        executable,
    )


def test_windows_install_registers_all_three_browser_hosts():
    installer = (ROOT / "build/installer.nsh").read_text(encoding="utf-8")
    bundle = (ROOT / "electron-builder.yml").read_text(encoding="utf-8")
    for vendor in ("Microsoft\\Edge", "Google\\Chrome", "Mozilla"):
        assert f"Software\\{vendor}\\NativeMessagingHosts\\com.pricemonitor.jd_edge" in installer
    assert "backend/com.pricemonitor.jd_edge.json" in bundle


def test_backend_dispatches_firefox_native_host_invocation(monkeypatch, tmp_path):
    from app.main import main

    expected = [str(tmp_path / "com.pricemonitor.jd_edge.json"), FIREFOX_EXTENSION_ID]
    monkeypatch.setattr("app.native_host.main", lambda args: 17 if args == expected else 18)
    assert main(expected) == 17


def test_native_host_forwards_browser_identity(monkeypatch, tmp_path):
    from app.native_host import relay

    config = tmp_path / "bridge.json"
    config.write_text(json.dumps({"port": 12345, "token": "a" * 64}), encoding="utf-8")
    monkeypatch.setattr("app.native_host.runtime_file", lambda: config)
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(json.loads(request.data))
        return io.BytesIO(b'{"job":null}')

    monkeypatch.setattr("app.native_host.urlopen", fake_urlopen)
    relay({"action": "claim", "browser": "chrome", "capabilities": ["jd"], "protocol_version": 2})
    relay({"action": "claim", "browser": "edge"}, forced_browser="firefox")

    assert requests[0]["browser"] == "chrome"
    assert requests[0]["protocol_version"] == 2
    assert requests[1]["browser"] == "firefox"
