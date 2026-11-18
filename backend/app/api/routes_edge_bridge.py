from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.edge_bridge import edge_bridge

router = APIRouter(prefix="/edge", tags=["edge"])


@router.get("/status")
async def status() -> dict:
    return {
        "selected_browser": edge_bridge.selected_browser,
        "jd_frequency_warning": edge_bridge.jd_pacer.frequency_warning,
        "protocol_version": edge_bridge.protocol_versions.get(edge_bridge.selected_browser, 1),
        "connected_browsers": edge_bridge.connected_browsers(),
        "connected": edge_bridge.connected("jd"),
        "platforms": [
            platform for platform in ("jd", "taobao") if edge_bridge.connected(platform)
        ],
        "pending": len(edge_bridge.pending),
    }


class ClaimRequest(BaseModel):
    browser: Literal["edge", "chrome", "firefox"] = "edge"
    capabilities: list[str] = Field(default_factory=lambda: ["jd"], max_length=3)
    protocol_version: int = Field(default=1, ge=1, le=2)


class PageObservation(BaseModel):
    browser: Literal["edge", "chrome", "firefox"] = "edge"
    url: str = Field(default="", max_length=2048)
    title: str = Field(default="", max_length=1024)
    title_texts: list[str] = Field(default_factory=list, max_length=100)
    body: str = Field(default="", max_length=500_000)
    visibility_state: Literal["visible", "hidden", "prerender", "unknown"] = "unknown"
    reused_tab: bool = False
    primary_text: str = Field(default="", max_length=20_000)
    primary_price_texts: list[str] = Field(default_factory=list, max_length=30)
    price_texts: list[str] = Field(default_factory=list, max_length=100)
    shop_texts: list[str] = Field(default_factory=list, max_length=100)
    coupon_texts: list[str] = Field(default_factory=list, max_length=100)
    html: str = Field(default="", max_length=750_000)
    error: str | None = Field(default=None, max_length=300)


@router.post("/claim")
async def claim(payload: ClaimRequest) -> dict:
    capabilities = set(payload.capabilities)
    return {"job": edge_bridge.claim(capabilities, payload.browser, payload.protocol_version)}


@router.post("/result/{request_id}")
async def result(request_id: str, payload: PageObservation) -> dict:
    return {
        "accepted": edge_bridge.submit(
            request_id, payload.model_dump(exclude={"browser"}), payload.browser
        )
    }
