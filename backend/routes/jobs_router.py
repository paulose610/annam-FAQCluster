import _job_ctl
from fastapi import APIRouter, HTTPException

from backend.jobs import jobs

router = APIRouter()


@router.get("/jobs")
def list_jobs():
    return list(jobs.values())


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/jobs/{job_id}/stop")
def stop_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] != "running":
        raise HTTPException(
            status_code=409,
            detail=f"job is not running (status={job['status']})",
        )
    _job_ctl.cancel(job_id)
    jobs[job_id]["status"] = "stopped"
    return {"job_id": job_id, "status": "stopped"}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] == "running":
        raise HTTPException(status_code=409, detail="cannot delete a running job")
    del jobs[job_id]
    return {"deleted": job_id}
