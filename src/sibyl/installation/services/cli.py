"""Explicit service CLI; preview/status do not import or start the application."""

import argparse
import json
import os
import sys
from pathlib import Path

from sibyl.installation.services.base import ServiceConfig, clean_path
from sibyl.installation.services.manager import service_manager
from sibyl.paths import default_data_dir


def main(argv=None):
    command = argparse.ArgumentParser(
        prog="sibyl service",
        description="Manage one current-user Sibyl login service. No admin/root service is installed.",
    )
    command.add_argument(
        "action", choices=["preview", "install", "status", "start", "stop", "restart", "uninstall"]
    )
    command.add_argument("--data-dir", type=Path, help="Workspace path; never moved or deleted.")
    command.add_argument("--port", type=int, help="Loopback port, default 8000.")
    command.add_argument(
        "--env-file",
        type=Path,
        help="Explicit private environment file; values are not copied into the service definition.",
    )
    command.add_argument("--dashboard-dir", type=Path, help="Explicit built dashboard override.")
    command.add_argument(
        "--replace", action="store_true", help="Replace a stopped, marked Sibyl definition deliberately."
    )
    args = command.parse_args(argv)
    if args.replace and args.action != "install":
        command.error("--replace applies only to install.")
    if args.action not in {"preview", "install"} and any(
        (args.data_dir, args.port, args.env_file, args.dashboard_dir, args.replace)
    ):
        command.error("Launch choices and --replace apply only to preview/install.")
    try:
        owner = service_manager()
        if args.action in {"preview", "install"}:
            config = ServiceConfig(
                executable=clean_path(sys.executable),
                data_dir=clean_path(args.data_dir or os.environ.get("SIBYL_DATA_DIR") or default_data_dir()),
                port=8000 if args.port is None else args.port,
                env_file=clean_path(args.env_file) if args.env_file else None,
                dashboard_dir=clean_path(args.dashboard_dir) if args.dashboard_dir else None,
            )
            result = (
                owner.preview(config)
                if args.action == "preview"
                else owner.install(config, replace=args.replace)
            )
        else:
            result = getattr(owner, args.action)()
        print(json.dumps(result, indent=2))
    except ValueError as exc:
        command.error(str(exc))
    except OSError:
        command.error(
            "A service file could not be accessed. Check user permissions; workspace data was not removed."
        )
