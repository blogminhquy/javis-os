"""Open an ordinary skill's resolved source without following a swapped parent."""
from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from pathlib import Path


def _windows_descriptor_path(descriptor: int) -> Path:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    final_path = kernel.GetFinalPathNameByHandleW
    final_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    final_path.restype = wintypes.DWORD
    handle = msvcrt.get_osfhandle(descriptor)
    size = final_path(handle, None, 0, 0)
    if not 0 < size < 32768:
        raise OSError('skill_descriptor_path_unavailable')
    buffer = ctypes.create_unicode_buffer(size + 1)
    written = final_path(handle, buffer, len(buffer), 0)
    if not 0 < written < len(buffer):
        raise OSError('skill_descriptor_path_unavailable')
    value = buffer.value
    if value.startswith('\\\\?\\UNC\\'):
        value = '\\\\' + value[8:]
    elif value.startswith('\\\\?\\'):
        value = value[4:]
    return Path(value)


def _posix_open(path: Path) -> int:
    # Walk from the filesystem root using already-open directory handles. A
    # renamed/replaced parent cannot redirect a subsequent component lookup.
    if (os.open not in os.supports_dir_fd or not hasattr(os, 'O_NOFOLLOW')
            or not hasattr(os, 'O_DIRECTORY') or not hasattr(os, 'O_NONBLOCK')):
        raise OSError('skill_anchored_open_unavailable')
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0)
    descriptors = []
    try:
        directory = os.open(path.anchor, directory_flags)
        descriptors.append(directory)
        for component in path.parts[1:-1]:
            directory = os.open(component, directory_flags, dir_fd=directory)
            descriptors.append(directory)
        return os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                       | getattr(os, 'O_CLOEXEC', 0), dir_fd=directory)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


@contextmanager
def open_skill_source(root: Path, path: Path, max_bytes: int):
    """Authenticate the actual regular-file descriptor before any body read."""
    path.relative_to(root)
    if not root.is_absolute() or not path.is_absolute():
        raise OSError('skill_absolute_source_required')
    if os.name == 'posix':
        descriptor = _posix_open(path)
    elif os.name == 'nt':
        descriptor = os.open(path, os.O_RDONLY | os.O_BINARY | getattr(os, 'O_NOINHERIT', 0))
    else:
        raise OSError('skill_descriptor_platform_unavailable')
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not 0 <= opened.st_size <= max_bytes:
            raise OSError('skill_descriptor_not_bounded_regular_file')
        if os.name == 'nt':
            # This is the kernel's path of the open handle, not a fresh resolution
            # of the caller pathname (which could already have been restored).
            actual = _windows_descriptor_path(descriptor)
            actual.relative_to(root)
            if actual != path:
                raise OSError('skill_descriptor_source_changed')
        stream = os.fdopen(descriptor, 'rb')
        descriptor = None
        with stream:
            yield stream
    finally:
        if descriptor is not None:
            os.close(descriptor)
