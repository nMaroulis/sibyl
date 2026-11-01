"""Resolve packaged dashboard assets and serve client-side routes from the API origin."""

from pathlib import Path

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


def dashboard_directory(override: Path | None = None) -> Path | None:
    """Prefer an explicit build, then bundled assets, then a source checkout's build."""
    if override is not None:
        directory = override.expanduser().resolve()
        if not (directory / "index.html").is_file():
            raise ValueError("SIBYL_DASHBOARD_DIR must contain a built dashboard index.html.")
        return directory
    package = Path(__file__).resolve().parents[1]
    candidates = [package / "web"]
    if package.parent.name == "src":
        candidates.append(package.parent.parent / "frontend" / "dist")
    return next((directory for directory in candidates if (directory / "index.html").is_file()), None)


class DashboardFiles(StaticFiles):
    """Use the SPA entry for page navigation, never for missing API routes or assets."""

    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            # Starlette supplies filesystem paths, which use backslashes on Windows.
            route_path = path.replace("\\", "/")
            first = route_path.split("/", 1)[0]
            if exc.status_code != 404 or first in {"api", "assets", "health", "docs", "redoc"}:
                raise
            if "." in route_path.rsplit("/", 1)[-1]:
                raise
            response = await super().get_response("index.html", scope)
        if response.media_type == "text/html":
            response.headers["Cache-Control"] = "no-cache"
        return response


def mount_dashboard(app: FastAPI, override: Path | None = None) -> None:
    """Attach the optional dashboard after API routes; API-only editable checkouts still work."""
    directory = dashboard_directory(override)
    if directory is not None:
        app.mount("/", DashboardFiles(directory=directory, html=True), name="dashboard")
