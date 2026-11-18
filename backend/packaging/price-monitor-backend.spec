# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-folder build for the PriceMonitor Python sidecar.

The Electron installer copies ``backend/dist/price-monitor-backend`` into
``resources/backend``. Playwright's driver is bundled, but browsers are not:
the app always launches the system Edge via ``channel="msedge"``.
"""

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

backend_root = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821
entry_point = os.path.join(backend_root, "app", "main.py")

datas = []
binaries = []
hiddenimports = []

# Playwright ships a driver executable under its package directory.
playwright_datas, playwright_binaries, playwright_hiddenimports = collect_all("playwright")
datas += playwright_datas
binaries += playwright_binaries
hiddenimports += playwright_hiddenimports

for package in ("uvicorn", "apscheduler"):
    hiddenimports += collect_submodules(package)

hiddenimports += collect_submodules("keyring.backends")
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "apscheduler.executors.asyncio",
    "apscheduler.jobstores.memory",
    "apscheduler.triggers.interval",
    "keyring.backends.Windows",
    "sqlalchemy.dialects.sqlite",
]

for package in (
    "fastapi",
    "uvicorn",
    "pydantic",
    "sqlalchemy",
    "apscheduler",
    "playwright",
    "keyring",
    "loguru",
    "httpx",
):
    try:
        datas += copy_metadata(package)
    except Exception:
        pass

a = Analysis(
    [entry_point],
    pathex=[backend_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "pytest", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="price-monitor-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="price-monitor-backend",
)
