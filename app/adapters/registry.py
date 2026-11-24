from app.adapters.base import PlatformAdapter
from app.adapters.instagram_manual import InstagramManualAdapter
from app.adapters.mock_platform import MockPlatformAdapter


def adapter_for(platform: str) -> PlatformAdapter:
    return {"instagram": InstagramManualAdapter, "mock": MockPlatformAdapter}.get(platform, InstagramManualAdapter)()
