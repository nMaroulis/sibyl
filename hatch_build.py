"""Bundle the already-built dashboard; editable development never requires Node.js."""

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class DashboardBuildHook(BuildHookInterface):
    """Include the same UI in wheels and source archives without running build commands."""

    def initialize(self, version, build_data):
        if version == "editable":
            return
        root = Path(self.root)
        # A source archive already carries the dashboard inside the Python package.
        bundled = root / "src" / "sibyl" / "web"
        if (bundled / "index.html").is_file():
            return
        dashboard = root / "frontend" / "dist"
        if not (dashboard / "index.html").is_file():
            raise RuntimeError("Build the dashboard before packaging Sibyl: npm ci && npm run build")
        destination = "src/sibyl/web" if self.target_name == "sdist" else "sibyl/web"
        build_data["force_include"][str(dashboard)] = destination
