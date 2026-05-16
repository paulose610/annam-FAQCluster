import asyncio
import subprocess
import sys
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from fastapi import BackgroundTasks

import _job_ctl

EXECUTOR = ThreadPoolExecutor()

jobs: dict[str, dict] = {}

JOB_TYPE_IDS: dict[str, int] = {
    "pre": 1,
    "pipeline": 2,
    "post": 3,
    "full": 4,
    "pop": 5,
}

_tl = threading.local()


class _JobStdout:
    """Routes print() output to the current job's stdout buffer, thread-safely."""
    def __init__(self, original):
        self._orig = original

    def write(self, data):
        job_id = getattr(_tl, "job_id", None)
        if job_id and job_id in jobs:
            jobs[job_id]["stdout"] += data
        self._orig.write(data)

    def flush(self):
        self._orig.flush()

    def __getattr__(self, name):
        return getattr(self._orig, name)


sys.stdout = _JobStdout(sys.stdout)


async def _run_job(job_id: str, fn: Callable[[], None]) -> None:
    jobs[job_id]["status"] = "running"
    loop = asyncio.get_running_loop()

    def _wrapped():
        _tl.job_id = job_id
        _job_ctl.set_job_id(job_id)
        try:
            fn()
        finally:
            _tl.job_id = None
            _job_ctl.set_job_id(None)
            _job_ctl.deregister_proc()

    try:
        await loop.run_in_executor(EXECUTOR, _wrapped)
        if _job_ctl.is_cancelled(job_id):
            jobs[job_id]["status"] = "stopped"
            jobs[job_id]["stderr"] = "stopped by user"
        else:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["stderr"] = ""
    except _job_ctl.JobCancelled:
        jobs[job_id]["status"] = "stopped"
        jobs[job_id]["stderr"] = "stopped by user"
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
        if _job_ctl.is_cancelled(job_id):
            jobs[job_id]["status"] = "stopped"
            jobs[job_id]["stderr"] = "stopped by user"
        else:
            jobs[job_id]["status"] = "done" if code == 0 else "failed"
            jobs[job_id]["stderr"] = f"SystemExit({code}): {code}"
    except subprocess.CalledProcessError as exc:
        if _job_ctl.is_cancelled(job_id):
            jobs[job_id]["status"] = "stopped"
            jobs[job_id]["stderr"] = "stopped by user"
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["stderr"] = (
                f"CalledProcessError (returncode={exc.returncode}): "
                f"{exc.cmd!r}\n{traceback.format_exc()}"
            )
    except Exception:
        if _job_ctl.is_cancelled(job_id):
            jobs[job_id]["status"] = "stopped"
            jobs[job_id]["stderr"] = "stopped by user"
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["stderr"] = traceback.format_exc()
    finally:
        _job_ctl.cleanup(job_id)


def _submit(fn: Callable[[], None], background: BackgroundTasks, job_type: str) -> dict:
    job_id = str(uuid.uuid4())
    _job_ctl.make_event(job_id)
    jobs[job_id] = {
        "job_id": job_id,
        "job_type": job_type,
        "job_type_id": JOB_TYPE_IDS[job_type],
        "status": "pending",
        "stdout": "",
        "stderr": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    background.add_task(_run_job, job_id, fn)
    return {
        "job_id": job_id,
        "job_type": job_type,
        "job_type_id": JOB_TYPE_IDS[job_type],
        "status": "pending",
    }
