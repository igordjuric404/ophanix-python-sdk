# SPDX-License-Identifier: MIT
"""Validate standalone SDK release artifacts before publishing."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path


EXPECTED_PACKAGE_FILES = (
    "ophanix_tool_gateway/__init__.py",
    "ophanix_tool_gateway/sdk.py",
    "ophanix_tool_gateway/py.typed",
)
FORBIDDEN_ARTIFACT_MARKERS = (
    ".db",
    ".sqlite",
    "__pycache__",
    ".pyc",
    "node_modules/",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Directory for generated artifacts. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--skip-twine-check",
        action="store_true",
        help="Skip metadata validation with twine.",
    )
    parser.add_argument(
        "--require-dependency-audit",
        action="store_true",
        help="Run pip-audit after artifact validation. Install .[security] first.",
    )
    parser.add_argument(
        "--strict-git",
        action="store_true",
        help="Require a clean SDK git state and a tag matching the package version.",
    )
    parser.add_argument(
        "--expected-tag",
        help="Expected release tag. Defaults to v<project.version> when --strict-git is used.",
    )
    args = parser.parse_args()

    package_root = Path(__file__).resolve().parents[1]
    if args.strict_git:
        _validate_git_state(package_root, expected_tag=args.expected_tag)
    if args.skip_twine_check:
        print("WARNING: twine metadata validation skipped; release-manifest.json records this.")
    with _artifact_directory(args.out_dir) as artifact_dir:
        _run_build(package_root, artifact_dir)
        wheel = _single_artifact(artifact_dir, "*.whl")
        sdist = _single_artifact(artifact_dir, "*.tar.gz")
        _validate_wheel(wheel)
        _validate_sdist(sdist)
        _validate_installed_wheel(wheel)
        if not args.skip_twine_check:
            _run_module(
                "twine",
                ["check", str(wheel), str(sdist)],
                package_root,
                missing_hint="Install release extras first: python3 -m pip install '.[release]'",
            )
        if args.require_dependency_audit:
            _validate_runtime_dependency_audit(wheel)
        sbom = _write_minimal_sbom(artifact_dir, package_root=package_root, artifacts=[wheel, sdist])
        _write_release_manifest(
            artifact_dir,
            package_root=package_root,
            artifacts=[wheel, sdist],
            sbom=sbom,
            dependency_audit_required=args.require_dependency_audit,
            strict_git=args.strict_git,
            twine_check_skipped=args.skip_twine_check,
        )
        print(f"Release artifacts validated in {artifact_dir}")
    return 0


class _artifact_directory:
    def __init__(self, requested: Path | None) -> None:
        self.requested = requested
        self.path: Path | None = None
        self._temporary: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        if self.requested is not None:
            self.path = self.requested.resolve()
            if self.path.exists():
                shutil.rmtree(self.path)
            self.path.mkdir(parents=True)
            return self.path
        self._temporary = tempfile.TemporaryDirectory(prefix="ophanix-sdk-release-")
        self.path = Path(self._temporary.name)
        return self.path

    def __exit__(self, *_exc_info: object) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()


def _run_build(package_root: Path, artifact_dir: Path) -> None:
    _run_module(
        "build",
        ["--sdist", "--wheel", "--outdir", str(artifact_dir)],
        package_root,
        missing_hint="Install release extras first: python3 -m pip install '.[release]'",
    )


def _validate_git_state(package_root: Path, *, expected_tag: str | None) -> None:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=package_root,
        text=True,
        capture_output=True,
    )
    if status.returncode != 0:
        raise SystemExit((status.stdout + status.stderr).strip() or "git status failed")
    if status.stdout.strip():
        raise SystemExit("SDK release validation requires a clean SDK package worktree.")
    version_value = _project_version(package_root)
    expected = expected_tag or f"v{version_value}"
    tag = subprocess.run(
        ["git", "describe", "--tags", "--exact-match"],
        cwd=package_root,
        text=True,
        capture_output=True,
    )
    if tag.returncode != 0 or tag.stdout.strip() != expected:
        raise SystemExit(f"SDK release must be built from tag {expected}.")


def _project_version(package_root: Path) -> str:
    with (package_root / "pyproject.toml").open("rb") as handle:
        metadata = tomllib.load(handle)
    version_value = metadata.get("project", {}).get("version")
    if not isinstance(version_value, str) or not version_value:
        raise SystemExit("pyproject.toml is missing project.version")
    return version_value


def _run_module(module: str, args: list[str], cwd: Path, *, missing_hint: str) -> None:
    command = [sys.executable, "-m", module, *args]
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode == 0:
        if result.stdout:
            print(result.stdout, end="")
        return
    output = f"{result.stdout}{result.stderr}"
    if f"No module named {module}" in output:
        raise SystemExit(missing_hint)
    raise SystemExit(output.strip() or f"{' '.join(command)} failed")


def _single_artifact(artifact_dir: Path, pattern: str) -> Path:
    matches = sorted(artifact_dir.glob(pattern))
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one {pattern} artifact, found {len(matches)}")
    return matches[0]


def _validate_wheel(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    missing = [path for path in EXPECTED_PACKAGE_FILES if path not in names]
    if missing:
        raise SystemExit(f"Wheel is missing expected files: {', '.join(missing)}")
    _validate_archive_names(names, artifact="Wheel")
    if not any(name.endswith("LICENSE") for name in names):
        raise SystemExit("Wheel is missing a LICENSE file")
    if not any(name.endswith(".dist-info/METADATA") for name in names):
        raise SystemExit("Wheel is missing METADATA")


def _validate_sdist(sdist: Path) -> None:
    with tarfile.open(sdist, "r:gz") as archive:
        names = set(archive.getnames())
    missing = [
        f"src/{path}"
        for path in EXPECTED_PACKAGE_FILES
        if not any(name.endswith(f"/src/{path}") for name in names)
    ]
    if missing:
        raise SystemExit(f"Sdist is missing expected files: {', '.join(missing)}")
    _validate_archive_names(names, artifact="Sdist")
    for required in ["LICENSE", "CHANGELOG.md", "SECURITY.md", "MIGRATION.md"]:
        if not any(name.endswith(f"/{required}") for name in names):
            raise SystemExit(f"Sdist is missing {required}")


def _validate_archive_names(names: set[str], *, artifact: str) -> None:
    forbidden = [
        name
        for name in names
        if any(marker in name for marker in FORBIDDEN_ARTIFACT_MARKERS)
    ]
    if forbidden:
        raise SystemExit(
            f"{artifact} contains forbidden generated/local files: {', '.join(sorted(forbidden)[:20])}"
        )


def _validate_installed_wheel(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="ophanix-sdk-install-") as target:
        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--target",
                target,
                str(wheel),
            ],
            cwd=wheel.parent,
        )
        _run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; "
                    f"sys.path.insert(0, {target!r}); "
                    "import ophanix_tool_gateway as sdk; "
                    "assert sdk.OphanixToolGatewayClient; "
                    "assert sdk.ToolAuthenticationError"
                ),
            ],
            cwd=wheel.parent,
        )


def _validate_runtime_dependency_audit(wheel: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="ophanix-sdk-audit-") as target:
        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--target",
                target,
                str(wheel),
            ],
            cwd=wheel.parent,
        )
        _run_module(
            "pip_audit",
            ["--progress-spinner", "off", "--path", target],
            wheel.parent,
            missing_hint="Install security extras first: python3 -m pip install '.[security]'",
        )


def _write_release_manifest(
    artifact_dir: Path,
    *,
    package_root: Path,
    artifacts: list[Path],
    sbom: Path,
    dependency_audit_required: bool,
    strict_git: bool,
    twine_check_skipped: bool,
) -> None:
    manifest = {
        "package": "ophanix-python-sdk",
        "version": _project_version(package_root),
        "dependency_audit_required": dependency_audit_required,
        "sbom_provenance": {
            "included": True,
            "sbom_file": sbom.name,
            "sbom_sha256": _sha256_file(sbom),
            "provenance_requirement": (
                "GitHub publish workflow signs artifacts and attests provenance before external release."
            ),
        },
        "strict_git": strict_git,
        "twine_check_skipped": twine_check_skipped,
        "artifacts": [
            {
                "filename": artifact.name,
                "sha256": _sha256_file(artifact),
                "size_bytes": artifact.stat().st_size,
            }
            for artifact in artifacts
        ],
    }
    (artifact_dir / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_minimal_sbom(artifact_dir: Path, *, package_root: Path, artifacts: list[Path]) -> Path:
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "library",
                "name": "ophanix-python-sdk",
                "version": _project_version(package_root),
            },
            "tools": [{"name": "scripts/validate_release.py", "version": "1"}],
        },
        "components": [
            {
                "type": "file",
                "name": artifact.name,
                "hashes": [{"alg": "SHA-256", "content": _sha256_file(artifact)}],
            }
            for artifact in artifacts
        ],
    }
    path = artifact_dir / "ophanix-python-sdk.cdx.json"
    path.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str], *, cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit((result.stdout + result.stderr).strip())


if __name__ == "__main__":
    raise SystemExit(main())
