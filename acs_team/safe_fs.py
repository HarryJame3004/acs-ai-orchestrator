"""Linux dirfd file operations resist path/symlink replacement races."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path, PurePosixPath

from .security import contained_path


@contextmanager
def open_workspace(root: Path, relative: str, *, write: bool = False):
    if Path(relative).is_absolute():
        relative = str(Path(relative).relative_to(root.resolve()))
    contained_path(root, relative)
    parts = PurePosixPath(relative).parts
    if not parts or any(
        part.lower().startswith(".env")
        or part.lower()
        in {"auth.token", "credentials.json", "auth.json", "id_rsa", "id_ed25519"}
        for part in parts
    ):
        raise PermissionError(
            "Credential/control files are excluded from workspace tools"
        )
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descriptor = None
    anchor = None
    try:
        for part in parts[:-1]:
            if write:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=directory)
                except FileExistsError:
                    pass
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            os.close(directory)
            directory = child
        if write:
            try:
                created = os.open(
                    parts[-1],
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | os.O_NOFOLLOW
                    | os.O_NONBLOCK,
                    0o600,
                    dir_fd=directory,
                )
                os.close(created)
            except FileExistsError:
                pass
        anchor = os.open(parts[-1], os.O_PATH | os.O_NOFOLLOW, dir_fd=directory)
        metadata = os.fstat(anchor)
        import stat

        if not stat.S_ISREG(metadata.st_mode):
            raise PermissionError("Workspace tool requires regular files")
        # Hard-linked files could alias outside the workspace even without a symlink.
        if metadata.st_nlink != 1:
            raise PermissionError("Hard-linked files require explicit review")
        if not write and metadata.st_size > 1024 * 1024:
            raise ValueError("Read exceeds 1 MiB budget")
        descriptor = os.open(
            f"/proc/self/fd/{anchor}", os.O_WRONLY if write else os.O_RDONLY
        )
        if write:
            os.ftruncate(descriptor, 0)
        with os.fdopen(
            descriptor, "w" if write else "r", encoding="utf-8", errors="replace"
        ) as stream:
            descriptor = None
            yield stream
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if anchor is not None:
            os.close(anchor)
        os.close(directory)


def list_workspace(root: Path, relative: str) -> list[str]:
    if Path(relative).is_absolute():
        relative = str(Path(relative).relative_to(root.resolve()))
    contained_path(root, relative)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in PurePosixPath(relative).parts:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        with os.scandir(descriptor) as entries:
            result = []
            for entry in entries:
                result.append(entry.name)
                if len(result) >= 200:
                    break
            return result
    finally:
        os.close(descriptor)
