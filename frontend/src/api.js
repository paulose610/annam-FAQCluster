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

export async function getTree() {
  const res = await fetch('/files/tree');
  return _handleResponse(res);
}

export function downloadUrl(path) {
  return `/files/download/${path}`;
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

export async function uploadFile(formData, dest = '') {
  const url = dest ? `/files/upload?dest=${encodeURIComponent(dest)}` : '/files/upload';
  const res = await fetch(url, { method: 'POST', body: formData });
  return _handleResponse(res);
}

export async function uploadPopFile(formData, dest = '') {
  const url = dest ? `/pop/upload?dest=${encodeURIComponent(dest)}` : '/pop/upload';
  const res = await fetch(url, { method: 'POST', body: formData });
  return _handleResponse(res);
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
