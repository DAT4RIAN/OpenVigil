from __future__ import annotations

import ctypes
import gc
import importlib
import sys
from pathlib import Path
from typing import Any


def _windows_peak_resident_bytes() -> int:
    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("page_fault_count", ctypes.c_ulong),
            ("peak_working_set_size", ctypes.c_size_t),
            ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t),
            ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
            ("quota_non_paged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
        ]

    kernel32: Any = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi: Any = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    )
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
    return int(counters.peak_working_set_size)


def _proc_peak_resident_bytes() -> int | None:
    status_path = Path("/proc/self/status")
    if not status_path.is_file():
        return None
    for line in status_path.read_text(encoding="ascii").splitlines():
        if line.startswith("VmHWM:"):
            fields = line.split()
            if len(fields) >= 2:
                return int(fields[1]) * 1024
    return None


def peak_process_resident_bytes() -> int:
    """Return the OS process resident-memory high-water mark in bytes.

    This measures the complete worker process, including Python, Arrow, and
    native libraries, without instrumenting every Python allocation.
    """

    if sys.platform == "win32":
        value = _windows_peak_resident_bytes()
    else:
        value = _proc_peak_resident_bytes()
        if value is None:
            resource: Any = importlib.import_module("resource")
            maximum = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            value = maximum if sys.platform == "darwin" else maximum * 1024
    if value <= 0:
        raise RuntimeError("process resident-memory high-water mark is unavailable")
    return value


def trim_process_resident_memory() -> bool:
    """Return unused allocator pages to the OS between bounded worker phases."""

    gc.collect()
    if sys.platform == "win32":
        kernel32: Any = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi: Any = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.EmptyWorkingSet.argtypes = (ctypes.c_void_p,)
        psapi.EmptyWorkingSet.restype = ctypes.c_int
        return bool(psapi.EmptyWorkingSet(kernel32.GetCurrentProcess()))
    if sys.platform.startswith("linux"):
        libc: Any = ctypes.CDLL(None)
        malloc_trim = getattr(libc, "malloc_trim", None)
        if malloc_trim is None:
            return False
        malloc_trim.argtypes = (ctypes.c_size_t,)
        malloc_trim.restype = ctypes.c_int
        return bool(malloc_trim(0))
    return False


__all__ = ["peak_process_resident_bytes", "trim_process_resident_memory"]
