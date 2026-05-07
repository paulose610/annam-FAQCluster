import pytest
import httpx
from app import app

BASE = "http://test"


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE)


@pytest.mark.anyio
async def test_health():
    async with client() as c:
        r = await c.get("/")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_list_jobs_empty():
    async with client() as c:
        r = await c.get("/jobs")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.anyio
async def test_job_not_found():
    async with client() as c:
        r = await c.get("/jobs/nonexistent-id")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_list_outputs_no_dir(tmp_path, monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "ROOT_DIR", tmp_path)
    async with client() as c:
        r = await c.get("/files/outputs")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.anyio
async def test_list_root_csvs():
    async with client() as c:
        r = await c.get("/files/root")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.anyio
async def test_path_traversal_blocked():
    # httpx normalises ../ before sending, so the server sees a 404 non-matching route;
    # either 400 or 404 confirms the file was not served.
    async with client() as c:
        r = await c.get("/files/outputs/../app.py")
    assert r.status_code in (400, 404)


@pytest.mark.anyio
async def test_root_invalid_filename_no_csv():
    async with client() as c:
        r = await c.get("/files/root/somefile.txt")
    assert r.status_code == 400


@pytest.mark.anyio
async def test_root_invalid_filename_traversal():
    async with client() as c:
        r = await c.get("/files/root/subdir%2Fetc%2Fpasswd")
    assert r.status_code in (400, 404)


@pytest.mark.anyio
async def test_run_pre_returns_job_id():
    body = {
        "input": "/tmp/fake_raw.csv",
        "state": "Karnataka",
        "crops": ["Cotton", "Sugarcane"],
        "output": "/tmp/karna_norm.csv",
        "keep_intermediate": True,
    }
    async with client() as c:
        r = await c.post("/run/pre", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "job_id" in data
    assert data["status"] == "pending"


@pytest.mark.anyio
async def test_run_pipeline_returns_job_id():
    body = {
        "raw_file": "/tmp/fake_norm.csv",
        "crop": "Cotton",
    }
    async with client() as c:
        r = await c.post("/run/pipeline", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "job_id" in data
    assert data["status"] == "pending"


@pytest.mark.anyio
async def test_run_post_returns_job_id():
    body = {"input": "outputs/repair"}
    async with client() as c:
        r = await c.post("/run/post", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "job_id" in data
    assert data["status"] == "pending"


@pytest.mark.anyio
async def test_run_full_returns_job_id():
    body = {
        "raw_file": "/tmp/fake_raw.csv",
        "state": "Karnataka",
        "crops": ["Cotton"],
    }
    async with client() as c:
        r = await c.post("/run/full", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "job_id" in data
    assert data["status"] == "pending"


@pytest.mark.anyio
async def test_job_appears_after_submit():
    body = {"input": "outputs/repair"}
    async with client() as c:
        r = await c.post("/run/post", json=body)
        job_id = r.json()["job_id"]
        r2 = await c.get(f"/jobs/{job_id}")
    assert r2.status_code == 200
    assert r2.json()["job_id"] == job_id


@pytest.mark.anyio
async def test_jobs_list_after_submit():
    body = {"input": "outputs/repair"}
    async with client() as c:
        await c.post("/run/post", json=body)
        r = await c.get("/jobs")
    assert r.status_code == 200
    assert len(r.json()) == 1
