from __future__ import annotations

from contextlib import suppress
from datetime import datetime

import keyring
from loguru import logger
from sqlalchemy.orm import Session

from app.adapters.base import PriceQuote
from app.core.models import Listing, Notification, Product, ProductPriceSnapshot, utcnow
from app.notifiers.base import NotificationMessage
from app.notifiers.serverchan import ServerChanNotifier

KEYRING_SERVICE = "PriceMonitor"
SERVERCHAN_USERNAME = "serverchan"


def get_serverchan_key() -> str | None:
    try:
        return keyring.get_password(KEYRING_SERVICE, SERVERCHAN_USERNAME)
    except Exception as exc:
        logger.warning("Failed to read ServerChan key from keyring: {}", exc)
        return None


def set_serverchan_key(sendkey: str) -> None:
    keyring.set_password(KEYRING_SERVICE, SERVERCHAN_USERNAME, sendkey.strip())


def clear_serverchan_key() -> None:
    with suppress(Exception):
        keyring.delete_password(KEYRING_SERVICE, SERVERCHAN_USERNAME)


def is_notification_configured() -> bool:
    return bool(get_serverchan_key())


def format_cents(cents: int) -> str:
    value = cents / 100
    text = f"{value:,.2f}"
    return f"¥{text.removesuffix('.00')}"


def build_new_low_message(
    product: Product,
    listing: Listing,
    quote: PriceQuote,
    snapshot: ProductPriceSnapshot,
) -> NotificationMessage:
    current = snapshot.lowest_price_cents
    previous = snapshot.previous_low_cents
    source_label = "结算实付价" if quote.source == "checkout" else "预估到手价"
    lines = [
        f"**商品**：{product.name}",
        f"**规格**：{product.ram_gb}GB+{product.storage_gb}GB",
        f"**平台**：京东 · {listing.shop_name}",
        f"**到手价**：{format_cents(current)}（{source_label}）",
    ]
    if previous is not None:
        lines.append(f"**原史低**：{format_cents(previous)}")
        lines.append(f"**降幅**：{format_cents(previous - current)}")
    applied_coupons = [
        item.get("raw")
        for item in (quote.coupon_breakdown or [])
        if item.get("applied")
    ]
    if applied_coupons:
        lines.append(f"**已用券**：{'、'.join(str(item) for item in applied_coupons)}")
    lines.extend(
        [
            f"**链接**：[打开商品]({listing.url})",
            f"**时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "价格来自京东页面展示与可见券估算，实际以下单结算为准。",
        ]
    )
    return NotificationMessage(
        title=f"京东新低 {format_cents(current)} · {product.name}",
        body="\n\n".join(lines),
        url=listing.url,
    )


async def send_new_low_notification(
    db: Session,
    product: Product,
    listing: Listing,
    quote: PriceQuote,
    snapshot: ProductPriceSnapshot,
) -> Notification:
    message = build_new_low_message(product, listing, quote, snapshot)
    notification = Notification(
        product_id=product.id,
        product_price_snapshot_id=snapshot.id,
        channel="serverchan",
        status="pending",
        payload={"title": message.title, "body": message.body, "url": message.url},
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    sendkey = get_serverchan_key()
    if not sendkey:
        notification.status = "failed"
        notification.error_message = "ServerChan SendKey 未配置"
        db.commit()
        logger.warning("ServerChan key is not configured; notification skipped")
        return notification

    try:
        await ServerChanNotifier(sendkey).send(message)
    except Exception as exc:
        notification.status = "failed"
        notification.error_message = str(exc)
        db.commit()
        logger.exception("Failed to send ServerChan notification")
        return notification

    notification.status = "sent"
    notification.sent_at = utcnow()
    db.commit()
    return notification


async def send_test_notification() -> None:
    sendkey = get_serverchan_key()
    if not sendkey:
        raise ValueError("请先配置 ServerChan SendKey")
    await ServerChanNotifier(sendkey).send(
        NotificationMessage(
            title="PriceMonitor 测试通知",
            body="如果你收到这条消息，说明 ServerChan 推送已经配置成功。",
        )
    )
