from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from loguru import logger


class CaptureBrowserLauncher:
    """Start the user's selected browser only when the extension is offline."""

    def __init__(self, bootstrap_dir: Path | None = None) -> None:
        self._launch_lock = asyncio.Lock()
        self.bootstrap_dir = bootstrap_dir or Path(tempfile.gettempdir()) / "PriceMonitorCapture"

    @staticmethod
    def _candidates(browser: str) -> list[Path]:
        program_files = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
        program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"))
        local_app_data = Path(os.environ.get("LOCALAPPDATA", "C:/Users/Default/AppData/Local"))
        if browser == "edge":
            return [
                Path(path) for path in filter(None, [shutil.which("msedge.exe"), shutil.which("msedge")])
            ] + [
                program_files_x86 / "Microsoft/Edge/Application/msedge.exe",
                program_files / "Microsoft/Edge/Application/msedge.exe",
                local_app_data / "Microsoft/Edge/Application/msedge.exe",
            ]
        if browser == "chrome":
            return [
                Path(path) for path in filter(None, [shutil.which("chrome.exe"), shutil.which("chrome")])
            ] + [
                program_files / "Google/Chrome/Application/chrome.exe",
                program_files_x86 / "Google/Chrome/Application/chrome.exe",
                local_app_data / "Google/Chrome/Application/chrome.exe",
            ]
        if browser == "firefox":
            return [
                Path(path) for path in filter(None, [shutil.which("firefox.exe"), shutil.which("firefox")])
            ] + [
                program_files / "Mozilla Firefox/firefox.exe",
                program_files_x86 / "Mozilla Firefox/firefox.exe",
                local_app_data / "Mozilla Firefox/firefox.exe",
            ]
        raise ValueError("Unsupported capture browser")

    def find_executable(self, browser: str) -> Path | None:
        return next((path for path in self._candidates(browser) if path.is_file()), None)

    def _bootstrap_url(self, bootstrap_token: str) -> str:
        self.bootstrap_dir.mkdir(parents=True, exist_ok=True)
        marker = self.bootstrap_dir / f"capture-{bootstrap_token}.html"
        marker.write_text(
            "<!doctype html><meta charset='utf-8'><title>PriceMonitor 采价窗口</title>",
            encoding="utf-8",
        )
        return marker.resolve().as_uri()

    async def launch(self, browser: str, bootstrap_token: str) -> Path:
        """Open one uniquely marked window that the extension takes over."""
        async with self._launch_lock:
            executable = self.find_executable(browser)
            if executable is None:
                raise FileNotFoundError(f"未找到所选浏览器：{browser}")
            marker = self._bootstrap_url(bootstrap_token)
            if browser in {"edge", "chrome"}:
                arguments = [
                    str(executable), "--new-window", "--start-minimized",
                    "--no-first-run", marker,
                ]
            else:
                arguments = [str(executable), "-new-window", marker]
            await asyncio.to_thread(self._spawn, arguments)
            logger.info("Started {} for an isolated price capture window", browser)
            return executable

    @staticmethod
    def _spawn(arguments: list[str]) -> None:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = getattr(subprocess, "SW_SHOWMINNOACTIVE", 7)
        subprocess.Popen(
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )


capture_browser_launcher = CaptureBrowserLauncher()
