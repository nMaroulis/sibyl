"""A small launcher shared by source checkouts, installed wheels and Homebrew."""

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

from sibyl import __version__


def parser() -> argparse.ArgumentParser:
    """Describe launch options without importing the application or initializing services."""
    command = argparse.ArgumentParser(description="Run Sibyl's local dashboard and Python API.")
    command.add_argument("--version", action="version", version=f"Sibyl {__version__}")
    command.add_argument("--host", help="Bind address (default: SIBYL_HOST or 127.0.0.1).")
    command.add_argument("--port", type=int, help="HTTP port (default: SIBYL_PORT or 8000).")
    command.add_argument(
        "--data-dir", type=Path, help="Workspace directory containing the database and vault."
    )
    command.add_argument(
        "--dashboard-dir", type=Path, help="Override the bundled dashboard with a local build."
    )
    env = command.add_mutually_exclusive_group()
    env.add_argument(
        "--env-file", type=Path, help="Read this environment file instead of .env in this directory."
    )
    env.add_argument(
        "--no-env-file", action="store_true", help="Read environment variables only; ignore .env."
    )
    command.add_argument(
        "--open-browser", action="store_true", help="Open the dashboard after the server is ready."
    )
    return command


def _open_when_ready(server, stopped: threading.Event, url: str) -> None:
    """Wait for this server's startup, rather than opening a different process on an occupied port."""
    while not stopped.wait(0.1):
        if server.should_exit:
            return
        if server.started:
            try:
                if webbrowser.open(url):
                    return
            except (webbrowser.Error, OSError):
                pass
            print(f"Open {url} in your browser.", file=sys.stderr)
            return


def main(argv: list[str] | None = None) -> None:
    """Resolve CLI overrides once and serve that exact configuration without mutating the environment."""
    command = parser()
    args = command.parse_args(argv)
    if args.env_file is not None and not args.env_file.is_file():
        command.error("--env-file must name an existing file.")

    import uvicorn
    from pydantic import ValidationError

    from sibyl.api.app import create_app
    from sibyl.config import Settings

    values = {
        name: getattr(args, name)
        for name in ("host", "port", "data_dir", "dashboard_dir")
        if getattr(args, name) is not None
    }
    env_file = None if args.no_env_file else args.env_file or Path(".env")
    try:
        settings = Settings(_env_file=env_file, **values)
    except ValidationError as exc:
        # Pydantic's full error includes input values; never print credential-bearing configuration.
        fields = ", ".join(".".join(str(part) for part in error["loc"]) for error in exc.errors())
        command.error(f"Invalid configuration for: {fields}. Check the environment file and launch options.")
    if settings.host not in {"localhost", "127.0.0.1", "::1"} and not settings.api_token.get_secret_value():
        command.error("Set SIBYL_API_TOKEN before exposing the API beyond loopback.")
    try:
        app = create_app(settings)
    except ValueError as exc:
        command.error(str(exc))
    server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port))
    stopped = threading.Event()
    if args.open_browser:
        host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(settings.host, settings.host)
        host = f"[{host}]" if ":" in host else host
        threading.Thread(
            target=_open_when_ready, args=(server, stopped, f"http://{host}:{settings.port}"), daemon=True
        ).start()
    try:
        server.run()
    finally:
        stopped.set()
