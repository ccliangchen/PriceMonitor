from pathlib import Path

import pytest

from app.services.capture_browser import CaptureBrowserLauncher


@pytest.mark.parametrize(
    ("browser", "command"),
    [("edge", "--new-window"), ("chrome", "--new-window"), ("firefox", "-new-window")],
)
async def test_launcher_opens_a_marked_capture_window(
    monkeypatch, tmp_path, browser, command,
):
    launcher = CaptureBrowserLauncher(tmp_path)
    executable = Path(f"C:/{browser}/{browser}.exe")
    spawned = []
    monkeypatch.setattr(launcher, "find_executable", lambda selected: executable)
    monkeypatch.setattr(launcher, "_spawn", lambda arguments: spawned.append(arguments))

    result = await launcher.launch(browser, "abc123")

    assert result == executable
    assert spawned[0][0] == str(executable)
    assert command in spawned[0]
    marker = tmp_path / "capture-abc123.html"
    assert spawned[0][-1] == marker.resolve().as_uri()
    assert marker.is_file()


async def test_launcher_reports_missing_selected_browser(monkeypatch, tmp_path):
    launcher = CaptureBrowserLauncher(tmp_path)
    monkeypatch.setattr(launcher, "find_executable", lambda browser: None)
    with pytest.raises(FileNotFoundError, match="未找到所选浏览器"):
        await launcher.launch("chrome", "token")
