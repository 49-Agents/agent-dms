"""Offline release metadata guard; no publication or repository mutations."""
import argparse
import json
import re
import subprocess
import tomllib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-commit", help="Exact full commit approved for publication")
    parser.add_argument("--expected-version")
    parser.add_argument("--schema", type=Path, help="Downloaded official registry JSON schema")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    server = json.loads((root / "server.json").read_text())

    def require(condition, message):
        if not condition:
            raise SystemExit(message)

    version = project["version"]
    require(server["version"] == version, "Registry and package versions differ")
    require(project["license"] == "MIT", "Review a license change before release")
    require(project["name"] == "agent-dms", "Unexpected package identity")
    require(len(server["description"]) <= 100, "Registry description exceeds 100 characters")
    require(f"<!-- mcp-name: {server['name']} -->" in (root / "README.md").read_text(),
            "PyPI README is missing the exact registry ownership marker")
    require(project["urls"]["Repository"] == server["repository"]["url"], "Repository URLs differ")
    for package in server["packages"]:
        require(package["version"] == version and package["identifier"] == project["name"],
                "Registry package identity/version mismatch")
        require(package["transport"]["type"] == "stdio", "Review registry transport change")
    for path in ("LICENSE", "THIRD_PARTY_NOTICES.md", "SECURITY.md", "SUPPORT.md",
                 "CHANGELOG.md", "docs/INSTALL.md", "docs/RELEASING.md",
                 "docs/NATIVE-CLIENT-ACCEPTANCE.md", "examples/demo.py"):
        require((root / path).is_file(), f"Missing release file: {path}")
    # README URLs work in both GitHub and PyPI rendered descriptions; validate
    # their source destinations locally while the default branch is unpublished.
    prefix = "https://github.com/49-Agents/agent-dms/blob/main/"
    for path in re.findall(re.escape(prefix) + r"([^\s)]+)", (root / "README.md").read_text()):
        require((root / path.split("#", 1)[0]).is_file(), f"Broken README target: {path}")
    require(f"{version}" in (root / "CHANGELOG.md").read_text(), "Missing changelog version")
    if args.expected_version is not None:
        require(args.expected_version == version, "Requested release version differs from source")
    if args.expected_commit is not None:
        require(re.fullmatch(r"[0-9a-f]{40}", args.expected_commit), "Expected commit must be a full SHA")
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        require(args.expected_commit == actual, "Source does not match the approved commit")
        dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=normal"],
                                        cwd=root, text=True)
        require(not dirty, "Publication requires a clean source checkout")
    if args.schema:
        from jsonschema import Draft7Validator, FormatChecker
        schema = json.loads(args.schema.read_text())
        Draft7Validator.check_schema(schema)
        Draft7Validator(schema, format_checker=FormatChecker()).validate(server)
    print(f"Release metadata passed: agent-dms {version}; no publication performed")


if __name__ == "__main__":
    main()
