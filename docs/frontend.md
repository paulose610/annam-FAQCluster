# Frontend

The frontend is a **React 18 + Vite** single-page application that provides a UI for running pipelines, monitoring jobs, browsing outputs, and managing POP translations.

**Location**: `frontend/`
**Dev server**: `npm run dev` (proxies API to backend on port `6100`)
**Build**: `npm run build` → `dist/`

---

## File Structure

```
frontend/
├── package.json
├── vite.config.js
├── index.html
└── src/
    ├── main.jsx                    # React root mount
    ├── App.jsx                     # Top-level tab router
    ├── api.js                      # All backend API calls
    └── components/
        ├── Header.jsx
        ├── FunctionsPanel/
        │   ├── FunctionsPanel.jsx      # FAQ-Cluster main UI
        │   └── PopTranslationPanel.jsx # POP-Translation UI
        └── (additional UI sub-components)
```

---

## `App.jsx` — Tab Layout

Three tabs rendered at the top level:

| Tab | Component | Status |
|---|---|---|
| FAQ-Cluster | `FunctionsPanel` | Active |
| POP-Translation | `PopTranslationPanel` | Active |
| Outreach | *(placeholder)* | Coming soon |

---

## `api.js` — Backend API Client

All communication with the FastAPI backend is centralised in `api.js`. The base URL defaults to `http://localhost:6100`.

### File Operations

| Function | HTTP | Endpoint | Description |
|---|---|---|---|
| `getAppTree()` | GET | `/app/tree` | Combined FAQ + POP file tree |
| `getTree()` | GET | `/files/tree` | FAQ-only file tree |
| `downloadUrl(path)` | — | `/files/download/{path}` | Returns a direct download URL string |
| `uploadFile(file, dest)` | POST | `/files/upload` or `/files/upload-chunk` | Auto-chunks files > 800 KB |
| `deleteFile(path)` | DELETE | `/files/{path}` | Delete a file |
| `renameFile(from, to)` | POST | `/files/rename/{from}` | Rename or move a file |
| `createFolder(path)` | POST | `/files/folders` | Create a directory |
| `uploadAudited(file, dest)` | POST | `/files/upload-audited` | Replace file with audited version |

### Pipeline Control

| Function | HTTP | Endpoint | Description |
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
  domains: [],               // QueryType filter (optional)
  output: "karnataka_norm",  // Output CSV name
  model: "google/gemma-4-26B-A4B-it",
  api_key: "",
  gpu_id: 1,
  batch_size: 32,
  grid_mode: "medium",       // "quick"|"medium"|"full"|"exhaustive"
  skip_dedup: false,
  // ...individual stage skip flags
}
```

### Job Management

| Function | HTTP | Endpoint | Description |
|---|---|---|---|
| `getJobs()` | GET | `/jobs` | List all jobs |
| `getJob(jobId)` | GET | `/jobs/{jobId}` | Full details: status, stdout, stderr |
| `stopJob(jobId)` | POST | `/jobs/{jobId}/stop` | Cancel a running job |
| `deleteJob(jobId)` | DELETE | `/jobs/{jobId}` | Remove job from history |

### POP-Translation

| Function | HTTP | Endpoint | Description |
|---|---|---|---|
| `getPopStates()` | GET | `/pop/states` | List available states |
| `getPopCrops(state)` | GET | `/pop/crops` | List crops for a state |
| `getPopDocs(state, crop)` | GET | `/pop/docs` | List PDFs |
| `getPopDataTree()` | GET | `/pop/data/tree` | Full POP data file tree |
| `runPop(body)` | POST | `/run/pop` | Start POP translation |
| `uploadPopFile(file, dest)` | POST | `/pop/upload` | Upload POP PDF |
| `deletePopFile(path)` | DELETE | `/pop/files/{path}` | Delete POP file |
| `deletePopFolder(path)` | DELETE | `/pop/folders/{path}` | Delete POP folder |
| `downloadPopUrl(path)` | — | `/pop/download/{path}` | POP download URL |

---

## `FunctionsPanel.jsx` — FAQ-Cluster UI

Main interface for the FAQ pipeline. Key user flows:

1. **Select state and crops** — dropdowns populated from pre-pipeline config or uploaded CSV.
2. **Configure pipeline** — model selection, grid mode, GPU, skip flags.
3. **Upload raw CSV** — calls `uploadFile()`, file lands in `app-data/`.
4. **Run pipeline** — calls `runFull()`, gets back `job_id`.
5. **Monitor job** — polls `getJob(job_id)` every ~2 s; displays live stdout stream.
6. **Browse results** — calls `getTree()` on completion; lists CSV outputs.
7. **Download FAQ** — calls `downloadUrl(path)` for the Q&A CSV.

---

## `PopTranslationPanel.jsx` — POP-Translation UI

Interface for PDF translation:

1. **Select state and crop** — `getPopStates()` + `getPopCrops()`.
2. **Select or upload PDF** — `getPopDocs()` to list existing; `uploadPopFile()` for new.
3. **Configure** — page range, concurrency, prompt file.
4. **Run** — calls `runPop()`; same job monitor pattern as FAQ pipeline.
5. **Download DOCX** — `downloadPopUrl(path)` for the translated Word document.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| react | 18.3.1 | UI framework |
| vite | 5.2.0 | Build tool and dev server |
| tailwindcss | 4.3.0 | Utility CSS framework |
| lucide-react | latest | Icon set |
| sonner | latest | Toast notifications |
