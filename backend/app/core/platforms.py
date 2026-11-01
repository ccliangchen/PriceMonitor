from __future__ import annotations

from urllib.parse import urlparse

PLATFORM_LABELS = {"jd": "京东", "taobao": "淘宝"}

JD_HOSTS = ("jd.com", "3.cn")
TAOBAO_HOSTS = ("taobao.com", "tmall.com", "tb.cn")


def _host_matches(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def detect_platform(url: str) -> str | None:
    value = url.strip()
    if not value:
        return None
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    host = urlparse(value).netloc.lower()
    if _host_matches(host, JD_HOSTS):
        return "jd"
    if _host_matches(host, TAOBAO_HOSTS):
        return "taobao"
    return None


def platform_label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform)
