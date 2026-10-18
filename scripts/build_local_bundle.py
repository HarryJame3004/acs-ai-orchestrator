"""Build a private source ZIP from committed Git blobs; never install or deploy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import zipfile


def build(repository: Path, destination: Path) -> dict:
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repository, check=True, capture_output=True
        ).stdout

    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Bundle destination must be new")
    commit = git("rev-parse", "HEAD").decode().strip()
    manifest = {
        "schema_version": 1,
        "commit": commit,
        "files": [],
        "excluded": [],
        "automatic_activation": False,
    }
    total = 0
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix=".acs-bundle-", suffix=".partial"
    ) as temporary:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for entry in git("ls-tree", "-r", "-z", commit).split(b"\0"):
                if not entry:
                    continue
                metadata, raw_name = entry.split(b"\t", 1)
                mode, kind, object_id = metadata.decode().split()
                name = raw_name.decode()
                path = PurePosixPath(name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in name
                    or "\x00" in name
                ):
                    raise ValueError("Unsafe archive path")
                forbidden = (
                    path.name.startswith(".env")
                    and not path.name.endswith(".example")
                    or path.name
                    in {
                        "auth.token",
                        "credentials.json",
                        "auth.json",
                        "id_rsa",
                        "id_ed25519",
                    }
                    or path.suffix
                    in {".pem", ".key", ".p12", ".db", ".sqlite", ".sqlite3"}
                    or any(p in {"attachments", ".aws", ".codex"} for p in path.parts)
                )
                if forbidden or mode == "120000" or kind != "blob":
                    manifest["excluded"].append(name)
                    continue
                size = int(git("cat-file", "-s", object_id))
                if size > 4 * 1024 * 1024 or total + size > 32 * 1024 * 1024:
                    raise ValueError("Bundle exceeds source size budget")
                data = git("cat-file", "blob", object_id)
                total += len(data)
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o100755 if mode == "100755" else 0o100644) << 16
                archive.writestr(info, data)
                manifest["files"].append(
                    {
                        "path": name,
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
            manifest_info = zipfile.ZipInfo('ACS_BUNDLE_MANIFEST.json',date_time=(1980,1,1,0,0,0))
            manifest_info.compress_type = zipfile.ZIP_DEFLATED
            manifest_info.external_attr = 0o100644 << 16
            archive.writestr(manifest_info,json.dumps(manifest,indent=2)+'\n')
        temporary.flush()
        os.fsync(temporary.fileno())
        # link fails rather than overwriting if another process created the path.
        os.link(temporary.name, destination)
    return {
        "commit": commit,
        "files": len(manifest["files"]),
        "excluded": len(manifest["excluded"]),
        "source_bytes": total,
        "archive_bytes": destination.stat().st_size,
        "automatic_activation": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.repository, args.output)))


if __name__ == "__main__":
    main()
