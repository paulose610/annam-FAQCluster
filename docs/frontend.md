# Frontend

The frontend is a **React 18 + Vite** single-page application that provides a UI for running pipelines, monitoring jobs, browsing outputs, and managing POP translations.

**Location**: `frontend/`
**Dev server**: `npm run dev` (proxies FAQ API calls to the pipeline server on port `7000`)
**Build**: `npm run build` → `dist/` (served by nginx in production)

---

## File Structure

```
frontend/
├── package.json
├── vite.config.js
├── index.html
├── Dockerfile
└── src/
    ├── main.jsx                    # React root mount
    ├── App.jsx                     # Top-level tab router
    ├── api.js                      # All backend API calls
    └── components/
        ├── Header.jsx
        ├── FunctionsPanel/
        │   ├── FunctionsPanel.jsx      # FAQ-Cluster main UI
        │   ├── RunTile.jsx
        │   ├── StateTable.jsx
        │   ├── PopStateTable.jsx
        │   ├── ColumnFilter.jsx
        │   └── PopTranslationPanel.jsx # POP-Translation UI
        ├── FilesPanel/
        │   ├── FilesPanel.jsx
        │   ├── FileGroup.jsx
        │   └── FileRow.jsx
        └── JobsPanel/
            └── JobCard.jsx
```

---

## `App.jsx` — Tab Layout

Tabs rendered at the top level:

| Tab | Component | Description |
|---|---|---|
| FAQ-Cluster | `FunctionsPanel` | Run pipeline, browse outputs |
| POP-Translation | `PopTranslationPanel` | Translate agricultural PDFs |

---

## `api.js` — Backend API Client

All communication is centralised in `api.js`. Two base URLs are used:

```js
const FAQ_API = window.__FAQ_API_URL__ || "http://localhost:7000";
const POP_API = window.__POP_API_URL__ || "http://localhost:8000";
```

Both are injected at nginx startup from the `FAQ_API_URL` and `POP_API_URL` env vars in `docker-compose.yml`. For local dev, they fall back to `localhost:7000` and `localhost:8000`.

### FAQ Cluster — File Operations

| Function | HTTP | Endpoint (FAQ_API) | Description |
|---|---|---|---|
| `getTree()` | GET | `/files/tree` | FAQ file tree |
| `downloadUrl(path)` | — | `/files/download/{path}` | Direct download URL |
| `outputDownloadUrl(state, crop)` | — | `/app/output/{state}/{crop}` | Final output CSV URL |
| `uploadFile(file, dest)` | POST | `/files/upload` or `/files/upload-chunk` | Auto-chunks files > 800 KB |
| `deleteFile(path)` | DELETE | `/files/{path}` | Delete a file |
| `deleteFolder(path)` | DELETE | `/folders/{path}` | Delete a folder |
| `renameFile(from, to)` | POST | `/files/rename/{from}` | Rename or move a file |
| `createFolder(path)` | POST | `/files/folders` | Create a directory |
| `uploadAuditedFile(file, state, crop)` | POST | `/files/upload-audited` | Replace file with audited version |

### FAQ Cluster — Pipeline Control

| Function | HTTP | Endpoint (FAQ_API) | Description |
|---|---|---|---|
| `runPre(body)` | POST | `/run/pre` | Start pre-pipeline |
| `runPipeline(body)` | POST | `/run/pipeline` | Start main per-crop pipeline |
| `runPost(body)` | POST | `/run/post` | Start post-pipeline deduplication |
| `runFull(body)` | POST | `/run/full` | Start end-to-end workflow |

**`runFull` body shape**:
```js
{
  state: "Karnataka",
  crops: ["Cotton", "Sugarcane"],
  domains: [],                   // QueryType filter (optional)
  output: "karnataka_norm",      // Output CSV name
  model: "google/gemma-4-26B-A4B-it",
  api_key: "",
  gpu_id: 0,
  batch_size: 32,
  grid_mode: "medium",           // "quick"|"medium"|"full"|"exhaustive"
  skip_dedup: false,
  // ...individual stage skip flags
}
```

### FAQ Cluster — App Utilities

| Function | HTTP | Endpoint (FAQ_API) | Description |
|---|---|---|---|
| `getNextState(state, domains)` | GET | `/app/next-state` | Next versioned state folder name |
| `getStateTable()` | GET | `/app/state-table` | State/crop output summary table |

### FAQ Cluster — Job Management

| Function | HTTP | Endpoint (FAQ_API) | Description |
|---|---|---|---|
| `getJobs()` | GET | `/jobs` | List all jobs |
| `getJob(jobId)` | GET | `/jobs/{jobId}` | Full details: status, stdout, stderr |
| `stopJob(jobId)` | POST | `/jobs/{jobId}/stop` | Cancel a running job |
| `deleteJob(jobId)` | DELETE | `/jobs/{jobId}` | Remove job from history |

### POP-Translation (separate POP server)

All POP calls go to `POP_API` (the separate POP server):

| Function | HTTP | Endpoint (POP_API) | Description |
|---|---|---|---|
| `getPopStates()` | GET | `/pop/states` | List available states |
| `getPopCrops(state)` | GET | `/pop/crops` | List crops for a state |
| `getPopDocs(state, crop)` | GET | `/pop/docs` | List PDFs |
| `getPopDataTree()` | GET | `/pop/data/tree` | Full POP data file tree |
| `getPopOutputTree()` | GET | `/pop/output/tree` | POP output file tree |
| `getPopStateTable()` | GET | `/pop/state-table` | Summary of states and crop counts |
| `runPop(body)` | POST | `/run/pop` | Start POP translation job |
| `uploadPopFile(file, dest)` | POST | `/pop/upload` or `/pop/upload-chunk` | Upload POP PDF |
| `deletePopFile(path)` | DELETE | `/pop/files/{path}` | Delete POP file |
| `deletePopFolder(path)` | DELETE | `/pop/folders/{path}` | Delete POP folder |
| `createPopFolder(path)` | POST | `/pop/folders` | Create POP folder |
| `popDownloadUrl(path)` | — | `/pop/download/{path}` | POP file download URL |
| `popOutputDownloadUrl(state, crop, docName)` | — | `/pop/output` | Translated DOCX download URL |
| `uploadPopAuditedFile(file, state, crop, docName)` | POST | `/pop/upload-audited` | Upload reviewed translation |

---

## `FunctionsPanel.jsx` — FAQ-Cluster UI

Main interface for the FAQ pipeline. Key user flows:

1. **Select state and crops** — dropdowns populated from pre-pipeline config or uploaded CSV.
2. **Configure pipeline** — model selection, grid mode, GPU, skip flags.
3. **Upload raw CSV** — calls `uploadFile()`, file lands in `app-data/`.
4. **Run pipeline** — calls `runFull()`, gets back `job_id`.
5. **Monitor job** — polls `getJob(job_id)` every ~2 s; displays live stdout stream.
6. **Browse results** — calls `getStateTable()` on completion; lists per-state/crop outputs.
7. **Download FAQ** — calls `outputDownloadUrl(state, crop)` for the final CSV.

---

## `PopTranslationPanel.jsx` — POP-Translation UI

Interface for PDF translation (calls POP server):

1. **Select state and crop** — `getPopStates()` + `getPopCrops()`.
2. **Select or upload PDF** — `getPopDocs()` to list existing; `uploadPopFile()` for new.
3. **Configure** — page range, concurrency, prompt file.
4. **Run** — calls `runPop()`; same job monitor pattern as FAQ pipeline.
5. **Download DOCX** — `popOutputDownloadUrl(state, crop, docName)` for the translated Word document.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| react | 18.3.1 | UI framework |
| vite | 5.2.0 | Build tool and dev server |
| tailwindcss | 4.3.0 | Utility CSS framework |
| lucide-react | latest | Icon set |
| sonner | latest | Toast notifications |
