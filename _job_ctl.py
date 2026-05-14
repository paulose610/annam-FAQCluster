#!/usr/bin/env python3
"""Shared job control registry used by app.py and pipeline runner scripts.

Tracks the current subprocess per job thread so the stop endpoint can kill it.
Import from both app.py (for cancel/cleanup) and pipeline files (for register_proc).
"""

import threading
import subprocess
from typing import Optional

_tl = threading.local()
_active_procs: dict[str, subprocess.Popen] = {}
_cancel_events: dict[str, threading.Event] = {}


def set_job_id(job_id: Optional[str]) -> None:
    _tl.job_id = job_id


def current_job_id() -> Optional[str]:
    return getattr(_tl, "job_id", None)


def register_proc(proc: subprocess.Popen) -> None:
    """Call immediately after spawning a subprocess; enables stop to kill it."""
    jid = current_job_id()
    if jid:
        _active_procs[jid] = proc


def deregister_proc() -> None:
    jid = current_job_id()
    if jid:
        _active_procs.pop(jid, None)


def is_cancelled(job_id: str) -> bool:
    ev = _cancel_events.get(job_id)
    return ev.is_set() if ev else False


def cancel(job_id: str) -> None:
    ev = _cancel_events.get(job_id)
    if ev:
        ev.set()
    proc = _active_procs.pop(job_id, None)
    if proc and proc.poll() is None:
        proc.kill()


def make_event(job_id: str) -> threading.Event:
    ev = threading.Event()
    _cancel_events[job_id] = ev
    return ev


def cleanup(job_id: str) -> None:
    _cancel_events.pop(job_id, None)
    _active_procs.pop(job_id, None)
