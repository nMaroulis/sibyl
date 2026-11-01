"""Keep release versions synchronized, inspect packages and write artifact checksums."""

import argparse
import hashlib
import json
import re
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path


def validate_version(version: str) -> str:
    """Accept the stable release format shared by Python, npm and GitHub tags."""
    if not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
        raise ValueError("Use a stable MAJOR.MINOR.PATCH version, without a v prefix.")
    return version


def release_version(root: Path, tag: str = "") -> str:
    """Require Python, dashboard, docs and release tags to name the same stable version."""
    version = validate_version(tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"])
    for relative in ("package.json", "frontend/package.json", "docs/package.json"):
        if json.loads((root / relative).read_text())["version"] != version:
            raise ValueError(f"Version mismatch in {relative}.")
    source = (root / "src/sibyl/__init__.py").read_text()
    if not re.search(rf'^__version__ = "{re.escape(version)}"$', source, re.MULTILINE):
        raise ValueError("Python runtime version does not match package metadata.")
    npm_lock = json.loads((root / "package-lock.json").read_text())
    if npm_lock["version"] != version or any(
        npm_lock["packages"][workspace]["version"] != version for workspace in ("", "frontend", "docs")
    ):
        raise ValueError("Version mismatch in package-lock.json; use set-version to synchronize metadata.")
    uv_lock = tomllib.loads((root / "uv.lock").read_text())
    if not any(
        package["name"] == "sibyl" and package["version"] == version for package in uv_lock["package"]
    ):
        raise ValueError("Version mismatch in uv.lock; use set-version to synchronize metadata.")
    if tag and tag != f"v{version}":
        raise ValueError(f"Release tag must be v{version}.")
    return version


def set_version(root: Path, version: str, *, dry_run: bool = False) -> list[str]:
    """Update application/package/lock metadata together; leave release history untouched.

    Validate every target before writing any file. Dependencies are not resolved or
    upgraded, and a repeated invocation with the same version leaves files unchanged.
    """
    validate_version(version)
    changes = {}

    def replace(relative: str, pattern: str, replacement):
        path = root / relative
        original = path.read_text(encoding="utf-8")
        updated, count = re.subn(pattern, replacement, original, flags=re.MULTILINE)
        if count != 1:
            raise ValueError(f"Expected one version declaration in {relative}.")
        changes[path] = updated

    replace("pyproject.toml", r'^version = "[^"]+"$', f'version = "{version}"')
    replace("src/sibyl/__init__.py", r'^__version__ = "[^"]+"$', f'__version__ = "{version}"')
    replace(
        "uv.lock",
        r'(^\[\[package\]\]\nname = "sibyl"\nversion = ")[^"]+("$)',
        lambda match: match[1] + version + match[2],
    )
    for relative in ("package.json", "frontend/package.json", "docs/package.json", "package-lock.json"):
        path = root / relative
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = version
        if relative == "package-lock.json":
            for workspace in ("", "frontend", "docs"):
                data["packages"][workspace]["version"] = version
        changes[path] = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    changed = [path for path, updated in changes.items() if path.read_text(encoding="utf-8") != updated]
    if not dry_run:
        for path in changed:
            path.write_text(changes[path], encoding="utf-8")
    return [path.relative_to(root).as_posix() for path in changed]


def inspect_wheel(wheel: Path) -> str:
    """Reject incomplete packages before installing or publishing them."""
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata = next(name for name in names if name.endswith(".dist-info/METADATA"))
        info = Parser().parsestr(archive.read(metadata).decode())
        if info["Name"] != "sibyl":
            raise ValueError("Expected the Sibyl application wheel.")
        for required in ("sibyl/web/index.html", "sibyl/cli.py", "sibyl/api/dashboard.py"):
            if required not in names:
                raise ValueError(f"Incomplete wheel: missing {required}.")
        if not any(name.startswith("sibyl/web/assets/") and name.endswith(".js") for name in names):
            raise ValueError("Incomplete wheel: no built dashboard JavaScript.")
        if any(
            part in {".env", ".sibyl", "vault.key", "sibyl.db"} for name in names for part in name.split("/")
        ):
            raise ValueError("Workspace files must never be bundled.")
        return info["Version"]


def sha256(path: Path) -> str:
    """Hash an artifact without loading its entire contents into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    command = argparse.ArgumentParser(description=__doc__)
    commands = command.add_subparsers(dest="action", required=True)
    version = commands.add_parser("version")
    version.add_argument("--root", type=Path, default=Path.cwd())
    version.add_argument("--tag", default="")
    update = commands.add_parser(
        "set-version", help="Synchronize all release metadata without changing dependencies."
    )
    update.add_argument("version")
    update.add_argument("--root", type=Path, default=Path.cwd())
    update.add_argument("--dry-run", action="store_true")
    wheel = commands.add_parser("inspect-wheel")
    wheel.add_argument(
        "wheel", type=Path, nargs="?", help="Defaults to the current version's wheel in dist/."
    )
    checksums = commands.add_parser("checksums")
    checksums.add_argument("directory", type=Path)
    args = command.parse_args()
    try:
        if args.action == "version":
            print(f"version={release_version(args.root, args.tag)}")
        elif args.action == "set-version":
            changed = set_version(args.root, args.version, dry_run=args.dry_run)
            if changed:
                print(f"{'Would set' if args.dry_run else 'Set'} version to {args.version}.")
                for relative in changed:
                    print(relative)
            else:
                print(f"Release metadata already uses {args.version}.")
        elif args.action == "inspect-wheel":
            if args.wheel is None:
                args.wheel = Path("dist") / f"sibyl-{release_version(Path.cwd())}-py3-none-any.whl"
            print(f"Complete Sibyl {inspect_wheel(args.wheel)} wheel: {args.wheel.name}")
        else:
            artifacts = sorted(
                p
                for p in args.directory.iterdir()
                if p.is_file() and p.name != "SHA256SUMS" and not p.name.startswith(".")
            )
            (args.directory / "SHA256SUMS").write_text(
                "".join(f"{sha256(path)}  {path.name}\n" for path in artifacts), encoding="utf-8"
            )
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        command.error(str(exc))


if __name__ == "__main__":
    main()
