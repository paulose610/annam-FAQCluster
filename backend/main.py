import sys
from pathlib import Path

# Ensure project root is on sys.path so pipeline scripts import correctly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI
from backend import jobs  # noqa: F401 — must import first to install _JobStdout on sys.stdout
from backend.routes import faq_cluster, pop_translation, files, jobs_router
from backend.routes.files import app_data_tree
from backend.routes.pop_translation import get_pop_data_tree

app = FastAPI(title="FAQCluster API", redirect_slashes=False)

app.include_router(faq_cluster.router)
app.include_router(pop_translation.router)
app.include_router(files.router)
app.include_router(jobs_router.router)


@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/app/tree")
def app_combined_tree():
    """Single endpoint returning FAQ file tree + POP data tree."""
    faq = app_data_tree()
    pop = get_pop_data_tree()
    return {**faq, "pop_files": pop["files"]}
