import pytest


@pytest.fixture(autouse=True)
def clear_jobs():
    from app import jobs
    jobs.clear()
    yield
    jobs.clear()
