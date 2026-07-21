import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18421
DEFAULT_ALLOWED_ORIGINS = (
    "http://127.0.0.1:1420",
    "http://localhost:1420",
    "http://tauri.localhost",
    "tauri://localhost",
)


@dataclass(frozen=True, slots=True)
class ServerSettings:
    config_path: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS

    @classmethod
    def from_env(cls) -> "ServerSettings":
        config_path = os.environ.get("BUMBLEHIVE_CONFIG")
        allowed_origins = os.environ.get("BUMBLEHIVE_ALLOWED_ORIGINS")
        return cls(
            config_path=(
                Path(config_path).expanduser()
                if config_path
                else Path.home() / ".bumblehive" / "config.json"
            ),
            host=os.environ.get("BUMBLEHIVE_HOST", DEFAULT_HOST),
            port=int(os.environ.get("BUMBLEHIVE_PORT", DEFAULT_PORT)),
            allowed_origins=(
                tuple(
                    origin.strip()
                    for origin in allowed_origins.split(",")
                    if origin.strip()
                )
                if allowed_origins is not None
                else DEFAULT_ALLOWED_ORIGINS
            ),
        )
