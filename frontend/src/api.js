async function _handleResponse(res) {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch {
      // ignore parse error
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function getAppTree() {
  const res = await fetch('/app/tree');
  return _handleResponse(res);
}

export async function getTree() {
  const res = await fetch('/files/tree');
  return _handleResponse(res);
}

export function downloadUrl(path) {
  return `/files/download/${path}`;
}

export function outputDownloadUrl(state, crop) {
  return `/app/output/${encodeURIComponent(state)}/${encodeURIComponent(crop)}`;
}

export async function deleteFile(path) {
  const res = await fetch(`/files/${path}`, { method: 'DELETE' });
  return _handleResponse(res);
}

export async function renameFile(fromPath, toPath) {
  const res = await fetch(`/files/rename/${fromPath}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to: toPath }),
  });
  return _handleResponse(res);
}

export async function deleteFolder(path) {
  const res = await fetch(`/folders/${path}`, { method: 'DELETE' });
  return _handleResponse(res);
}

export async function createFolder(path) {
  const res = await fetch('/files/folders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  return _handleResponse(res);
}

const _CHUNK_SIZE = 800 * 1024; // 800 KB — safely under dev-tunnel nginx 1 MB limit

async function _uploadChunked(file, dest, chunkEndpoint, onProgress) {
  const totalChunks = Math.ceil(file.size / _CHUNK_SIZE);
  const uploadId = crypto.randomUUID();
  let result;
  for (let i = 0; i < totalChunks; i++) {
    const chunk = file.slice(i * _CHUNK_SIZE, Math.min((i + 1) * _CHUNK_SIZE, file.size));
    const params = new URLSearchParams({
      upload_id: uploadId,
      chunk_index: String(i),
      total_chunks: String(totalChunks),
      filename: file.name,
      dest: dest || '',
    });
    const res = await fetch(`${chunkEndpoint}?${params}`, {
      method: 'POST',
      body: chunk,
      headers: { 'Content-Type': 'application/octet-stream' },
    });
    result = await _handleResponse(res);
    onProgress?.(Math.round((i + 1) / totalChunks * 100));
  }
  return result;
}

export async function uploadFile(file, dest = '', onProgress) {
  if (file.size > _CHUNK_SIZE) return _uploadChunked(file, dest, '/files/upload-chunk', onProgress);
  const fd = new FormData();
  fd.append('file', file);
  const url = dest ? `/files/upload?dest=${encodeURIComponent(dest)}` : '/files/upload';
  const res = await fetch(url, { method: 'POST', body: fd });
  const result = await _handleResponse(res);
  onProgress?.(100);
  return result;
}

export async function uploadPopFile(file, dest = '', onProgress) {
  if (file.size > _CHUNK_SIZE) return _uploadChunked(file, dest, '/pop/upload-chunk', onProgress);
  const fd = new FormData();
  fd.append('file', file);
  const url = dest ? `/pop/upload?dest=${encodeURIComponent(dest)}` : '/pop/upload';
  const res = await fetch(url, { method: 'POST', body: fd });
  const result = await _handleResponse(res);
  onProgress?.(100);
  return result;
}

export async function getJobs() {
  const res = await fetch('/jobs');
  return _handleResponse(res);
}

export async function getJob(jobId) {
  const res = await fetch(`/jobs/${jobId}`);
  return _handleResponse(res);
}

export async function deleteJob(jobId) {
  const res = await fetch(`/jobs/${jobId}`, { method: 'DELETE' });
  return _handleResponse(res);
}

export async function stopJob(jobId) {
  const res = await fetch(`/jobs/${jobId}/stop`, { method: 'POST' });
  return _handleResponse(res);
}

export async function runPre(body) {
  const res = await fetch('/run/pre', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return _handleResponse(res);
}

export async function runPipeline(body) {
  const res = await fetch('/run/pipeline', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return _handleResponse(res);
}

export async function runPost(body) {
  const res = await fetch('/run/post', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return _handleResponse(res);
}

export async function runFull(body) {
  const res = await fetch('/run/full', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return _handleResponse(res);
}

export async function getNextState(state = '', domains = []) {
  const params = new URLSearchParams({ state });
  for (const d of domains) params.append('domains', d);
  const res = await fetch(`/app/next-state?${params}`);
  return _handleResponse(res);
}

export async function getStateTable() {
  const res = await fetch('/app/state-table');
  return _handleResponse(res);
}

export async function getPopStateTable() {
  const res = await fetch('/pop/state-table');
  return _handleResponse(res);
}

export async function uploadAuditedFile(file, state, crop) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('state', state);
  fd.append('crop', crop);
  const res = await fetch('/files/upload-audited', { method: 'POST', body: fd });
  return _handleResponse(res);
}

// --- POP Translation ---

export async function getPopStates() {
  const res = await fetch('/pop/states');
  return _handleResponse(res);
}

export async function getPopCrops(state) {
  const res = await fetch(`/pop/crops?state=${encodeURIComponent(state)}`);
  return _handleResponse(res);
}

export async function getPopDocs(state, crop) {
  const res = await fetch(`/pop/docs?state=${encodeURIComponent(state)}&crop=${encodeURIComponent(crop)}`);
  return _handleResponse(res);
}

export async function getPopDataTree() {
  const res = await fetch('/pop/data/tree');
  return _handleResponse(res);
}

export async function getPopOutputTree() {
  const res = await fetch('/pop/output/tree');
  return _handleResponse(res);
}

export async function runPop(body) {
  const res = await fetch('/run/pop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return _handleResponse(res);
}

export async function createPopFolder(path) {
  const res = await fetch('/pop/folders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  return _handleResponse(res);
}

export function popDownloadUrl(path) {
  return `/pop/download/${path}`;
}

export function popOutputDownloadUrl(state, crop, docName) {
  const params = new URLSearchParams({ state, crop, doc_name: docName });
  return `/pop/output?${params}`;
}

export async function deletePopFile(path) {
  const res = await fetch(`/pop/files/${path}`, { method: 'DELETE' });
  return _handleResponse(res);
}

export async function deletePopFolder(path) {
  const res = await fetch(`/pop/folders/${path}`, { method: 'DELETE' });
  return _handleResponse(res);
}

export async function uploadPopAuditedFile(file, state, crop, docName) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('state', state);
  fd.append('crop', crop);
  fd.append('doc_name', docName);
  const res = await fetch('/pop/upload-audited', { method: 'POST', body: fd });
  return _handleResponse(res);
}
