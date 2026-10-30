from app.adapters.base import PlatformAdapter

_ADAPTERS: dict[str, PlatformAdapter] = {}


def register(adapter: PlatformAdapter) -> None:
    _ADAPTERS[adapter.platform] = adapter


def get_adapter(platform: str) -> PlatformAdapter | None:
    return _ADAPTERS.get(platform)


def list_platforms() -> list[str]:
    return sorted(_ADAPTERS)
