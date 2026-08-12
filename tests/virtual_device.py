"""Deterministic host model of the small filesystem exposed to TartLab.

This is deliberately a TartLab test double, not an ESP32 emulator.  It maps
MicroPython-style absolute paths into a temporary host directory and records
each filesystem mutation so tests can inject an abrupt loss of power at a
specific operation.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable


@dataclass(frozen=True)
class Mutation:
    sequence: int
    operation: str
    path: str
    destination: str | None = None


class VirtualPowerLoss(BaseException):
    """An abrupt reset that device code must not catch as an ordinary error."""

    def __init__(self, mutation: Mutation):
        super().__init__(
            "virtual power loss after %s %s" %
            (mutation.operation, mutation.path))
        self.mutation = mutation


class _VirtualFile:
    def __init__(self, filesystem, stream, logical_path, writable):
        self._filesystem = filesystem
        self._stream = stream
        self._logical_path = logical_path
        self._writable = writable
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def __iter__(self):
        return iter(self._stream)

    def __next__(self):
        return next(self._stream)

    def __getattr__(self, name):
        return getattr(self._stream, name)

    @property
    def closed(self):
        return self._closed

    def write(self, data):
        result = self._stream.write(data)
        self._stream.flush()
        self._filesystem._record("write", self._logical_path)
        return result

    def writelines(self, lines):
        result = self._stream.writelines(lines)
        self._stream.flush()
        self._filesystem._record("write", self._logical_path)
        return result

    def truncate(self, size=None):
        result = self._stream.truncate(size)
        self._stream.flush()
        self._filesystem._record("truncate", self._logical_path)
        return result

    def close(self):
        if self._closed:
            return
        self._stream.close()
        self._closed = True
        if self._writable:
            self._filesystem._record("close_write", self._logical_path)


class VirtualOS:
    """The subset of ``os``/``uos`` used by TartLab's filesystem code."""

    sep = "/"

    def __init__(self, filesystem):
        self._filesystem = filesystem

    def stat(self, path):
        return os.stat(self._filesystem.host_path(path))

    def statvfs(self, path):
        # Match the tuple indices used by MicroPython: fragment size at 1,
        # total blocks at 2, and free blocks at 3.
        block_size = self._filesystem.block_size
        total_blocks = self._filesystem.capacity_bytes // block_size
        used_bytes = sum(
            item.stat().st_size for item in self._filesystem.root.rglob("*")
            if item.is_file())
        free_blocks = max(
            0, (self._filesystem.capacity_bytes - used_bytes) // block_size)
        return (
            block_size, block_size, total_blocks, free_blocks, free_blocks,
            0, 0, 255, 255, 255,
        )

    def listdir(self, path="/"):
        return os.listdir(self._filesystem.host_path(path))

    def mkdir(self, path):
        os.mkdir(self._filesystem.host_path(path))
        self._filesystem._record("mkdir", path)

    def remove(self, path):
        os.remove(self._filesystem.host_path(path))
        self._filesystem._record("remove", path)

    def rmdir(self, path):
        os.rmdir(self._filesystem.host_path(path))
        self._filesystem._record("rmdir", path)

    def rename(self, source, destination):
        os.rename(
            self._filesystem.host_path(source),
            self._filesystem.host_path(destination))
        self._filesystem._record("rename", source, destination)

    def getcwd(self):
        return "/"

    def sync(self):
        return None

    def urandom(self, size):
        return os.urandom(size)


class VirtualDeviceFS:
    """Map a device root into a host directory with deterministic faults."""

    def __init__(
            self, root: Path, *, capacity_bytes: int = 6_291_456,
            block_size: int = 4096):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.capacity_bytes = capacity_bytes
        self.block_size = block_size
        self.mutations: list[Mutation] = []
        self.os = VirtualOS(self)
        self._power_loss_predicate: Callable[[Mutation], bool] | None = None
        self._power_loss_occurrence = 1
        self._matching_mutations = 0

    def host_path(self, logical_path) -> Path:
        normalized = str(logical_path).replace("\\", "/")
        pure = PurePosixPath("/" + normalized.lstrip("/"))
        if any(part in ("", ".", "..") for part in pure.parts[1:]):
            raise ValueError("Unsafe virtual device path: %s" % logical_path)
        target = self.root.joinpath(*pure.parts[1:]).resolve()
        if os.path.commonpath((str(self.root), str(target))) != str(self.root):
            raise ValueError("Virtual device path escapes its root: %s" % logical_path)
        return target

    def logical_path(self, host_path: Path) -> str:
        relative = Path(host_path).resolve().relative_to(self.root)
        return "/" + relative.as_posix() if relative.parts else "/"

    def open(self, path, mode="r", *args, **kwargs):
        logical = "/" + str(path).replace("\\", "/").lstrip("/")
        writable = any(flag in mode for flag in "wax+")
        stream = open(self.host_path(logical), mode, *args, **kwargs)
        if writable:
            try:
                self._record("open_write", logical)
            except BaseException:
                stream.close()
                raise
        return _VirtualFile(self, stream, logical, writable)

    def arm_power_loss(
            self, predicate: Callable[[Mutation], bool], *, occurrence: int = 1):
        if occurrence < 1:
            raise ValueError("Power-loss occurrence must be positive")
        self._power_loss_predicate = predicate
        self._power_loss_occurrence = occurrence
        self._matching_mutations = 0

    def disarm_power_loss(self):
        self._power_loss_predicate = None
        self._matching_mutations = 0

    def clear_journal(self):
        self.mutations.clear()

    def _record(self, operation, path, destination=None):
        logical = "/" + str(path).replace("\\", "/").lstrip("/")
        logical_destination = None
        if destination is not None:
            logical_destination = "/" + str(destination).replace(
                "\\", "/").lstrip("/")
        mutation = Mutation(
            len(self.mutations) + 1, operation, logical,
            logical_destination)
        self.mutations.append(mutation)
        predicate = self._power_loss_predicate
        if predicate is None or not predicate(mutation):
            return
        self._matching_mutations += 1
        if self._matching_mutations == self._power_loss_occurrence:
            self.disarm_power_loss()
            raise VirtualPowerLoss(mutation)

    def snapshot(self, logical_paths: Iterable[str]) -> dict[str, bytes]:
        result = {}
        for logical_path in logical_paths:
            host = self.host_path(logical_path)
            if host.is_file():
                result[self.logical_path(host)] = host.read_bytes()
            elif host.is_dir():
                for child in sorted(
                        item for item in host.rglob("*") if item.is_file()):
                    result[self.logical_path(child)] = child.read_bytes()
        return result
