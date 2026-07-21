import uvicorn

from .app import app
from .settings import ServerSettings


def main() -> None:
    settings = ServerSettings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()

