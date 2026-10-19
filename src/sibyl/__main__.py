"""Command-line entry point for the Python API."""

import uvicorn

from sibyl.config import Settings


def main() -> None:
    """Serve the API using validated settings from the environment or ``.env``."""
    settings = Settings()
    if settings.host not in {"localhost", "127.0.0.1", "::1"} and not settings.api_token.get_secret_value():
        raise SystemExit("Set SIBYL_API_TOKEN before exposing the API beyond loopback.")
    uvicorn.run("sibyl.api.app:create_app", factory=True, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
