import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Square, FileText } from 'lucide-react';
import { MultiSelector, StateSelector } from './RunTile.jsx';
import { getPopStates, getPopCrops, getPopDocs, runPop, getJob, stopJob } from '../../api.js';
import PopStateTable from './PopStateTable.jsx';

const inputClass =
  'w-full bg-input border border-border rounded-md px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-ring transition-shadow';

const labelClass = 'text-xs font-medium text-foreground/70';

function parsePopOutput(stdout) {
  if (!stdout) return null;
  const lines = stdout.split('\n');
  let totalDocs = null;
  const docs = [];
  let currentIdx = -1;

  for (const line of lines) {
    const totalMatch = line.match(/\[POP\] Total docs: (\d+)/);
    if (totalMatch) { totalDocs = parseInt(totalMatch[1]); continue; }

    const processingMatch = line.match(/\[POP\] Processing: (.+)/);
    if (processingMatch) {
      docs.push({ name: processingMatch[1].trim(), pagesTotal: null, pagesDone: 0, status: 'running' });
      currentIdx = docs.length - 1;
      continue;
    }

    const startedMatch = line.match(/Translation stage started \| pages=(\d+)/);
    if (startedMatch && currentIdx >= 0) {
      docs[currentIdx].pagesTotal = parseInt(startedMatch[1]);
      continue;
    }

    const progressMatch = line.match(/Translation progress \| completed (\d+)\/(\d+)/);
    if (progressMatch && currentIdx >= 0) {
      docs[currentIdx].pagesDone = parseInt(progressMatch[1]);
      docs[currentIdx].pagesTotal = parseInt(progressMatch[2]);
      continue;
    }

    if (line.trim() === 'DONE' && currentIdx >= 0) {
      docs[currentIdx].status = 'done';
      continue;
    }
  }

  return { totalDocs, docs };
}

function PopProgress({ stdout }) {
  const data = parsePopOutput(stdout);
  if (!data || (data.totalDocs === null && data.docs.length === 0)) return null;

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border/50 bg-muted/10 px-3 py-2">
      {data.totalDocs !== null && (
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <FileText size={11} />
          <span>{data.docs.length} / {data.totalDocs} docs</span>
        </div>
      )}
      {data.docs.map((doc, i) => (
        <div key={i} className="flex flex-col gap-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-foreground truncate flex-1 min-w-0" title={doc.name}>{doc.name}</span>
            {doc.pagesTotal !== null && (
              <span className="text-[10px] text-muted-foreground shrink-0">
                {doc.pagesDone}/{doc.pagesTotal} pages
              </span>
            )}
          </div>
          {doc.pagesTotal !== null && (
            <div className="h-1 w-full bg-muted/50 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${doc.status === 'done' ? 'bg-green-500' : 'bg-blue-400 animate-pulse'}`}
                style={{ width: `${Math.round((doc.pagesDone / doc.pagesTotal) * 100)}%` }}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

const POP_TILE_KEY = 'tile:pop-translation';

export default function PopTranslationPanel({ onJobCreated }) {
  const [state, setState] = useState('');
  const [crop, setCrop] = useState('');
  const [docs, setDocs] = useState([]);
  const [concurrency, setConcurrency] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [tableRefreshKey, setTableRefreshKey] = useState(0);

  // Job tracking
  const [jobId, setJobId] = useState(null);
  const [jobData, setJobData] = useState(null);
  const [jobLabel, setJobLabel] = useState('');
  const pollRef = useRef(null);

  const [stateOptions, setStateOptions] = useState([]);
  const [cropOptions, setCropOptions] = useState([]);
  const [docOptions, setDocOptions] = useState([]);

  const formRef = useRef(null);
  const [stacked, setStacked] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => setStacked(!entry.isIntersecting),
      { threshold: 0 }
    );
    if (formRef.current) observer.observe(formRef.current);
    return () => observer.disconnect();
  }, []);

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }
  useEffect(() => () => stopPolling(), []);

  function startPolling(jid) {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const data = await getJob(jid);
        setJobData(data);
        if (data.status === 'done' || data.status === 'failed' || data.status === 'stopped') {
          stopPolling();
          setTableRefreshKey((k) => k + 1);
        }
      } catch { /* ignore */ }
    }, 3000);
  }

  // Restore running job from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem(POP_TILE_KEY);
    if (!saved) return;
    try {
      const { jobId: savedJid, label: savedLabel } = JSON.parse(saved);
      if (!savedJid) return;
      setJobLabel(savedLabel || '');
      getJob(savedJid).then((data) => {
        setJobId(savedJid);
        setJobData(data);
        if (data.status === 'running') startPolling(savedJid);
        else { setTableRefreshKey((k) => k + 1); }
      }).catch(() => localStorage.removeItem(POP_TILE_KEY));
    } catch { localStorage.removeItem(POP_TILE_KEY); }
  }, []);

  useEffect(() => {
    getPopStates()
      .then((data) => setStateOptions(data.states || []))
      .catch((err) => console.error('Failed to load POP states:', err));
  }, []);

  useEffect(() => {
    if (!state) {
      setCropOptions([]);
      setCrop('');
      setDocs([]);
      return;
    }
    getPopCrops(state)
      .then((data) => {
        setCropOptions(data.crops || []);
        setCrop('');
        setDocs([]);
      })
      .catch((err) => console.error('Failed to load POP crops:', err));
  }, [state]);

  useEffect(() => {
    if (!state || !crop) {
      setDocOptions([]);
      setDocs([]);
      return;
    }
    getPopDocs(state, crop)
      .then((data) => {
        setDocOptions(data.docs || []);
        setDocs([]);
      })
      .catch((err) => console.error('Failed to load POP docs:', err));
  }, [state, crop]);

  async function handleRun() {
    if (!state || !crop) return;
    const body = { state, crop, concurrency };
    if (docs.length > 0) body.docs = docs;
    const label = `${state} / ${crop}`;
    setSubmitting(true);
    try {
      const result = await runPop(body);
      const jid = result.job_id;
      setJobId(jid);
      setJobData({ job_id: jid, status: 'running', stdout: '', stderr: '' });
      setJobLabel(label);
      localStorage.setItem(POP_TILE_KEY, JSON.stringify({ jobId: jid, label }));
      toast.success(`POP job queued — ${jid.slice(0, 8)}`);
      if (onJobCreated) onJobCreated();
      startPolling(jid);
    } catch (err) {
      toast.error(err.message || 'Failed to start POP translation');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStop() {
    if (!jobId) return;
    try { await stopJob(jobId); } catch { /* ignore */ }
  }

  const isRunning = jobData?.status === 'running';
  const isSettled = jobData && !isRunning;
  const STATUS_COLORS = { done: 'text-green-400', failed: 'text-destructive', stopped: 'text-amber-400' };

  return (
    <div className="flex flex-col">
      <div ref={formRef} className="max-w-3xl mx-auto w-full">
      <div className="flex justify-center">
      <div className="w-full max-w-md bg-card rounded-lg border border-border shadow-sm p-5 flex flex-col gap-4">

      {isRunning && (
        <>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse flex-shrink-0" />
              <span className="text-sm font-bold text-foreground">Running</span>
              {jobLabel && <span className="text-xs bg-accent/50 border border-border rounded px-1.5 py-0.5 text-foreground">{jobLabel}</span>}
            </div>
            <button
              className="flex items-center gap-1 px-2.5 py-1 rounded border border-destructive/40 text-destructive hover:bg-destructive/10 text-xs transition-colors cursor-pointer"
              onClick={handleStop}
            >
              <Square size={11} /> Stop
            </button>
          </div>
          {jobData?.stdout && <PopProgress stdout={jobData.stdout} />}
        </>
      )}

      {isSettled && (
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold capitalize ${STATUS_COLORS[jobData.status] || 'text-muted-foreground'}`}>
            Last run: {jobData.status}
          </span>
          {jobLabel && <span className="text-xs bg-accent/50 border border-border rounded px-1.5 py-0.5 text-muted-foreground">{jobLabel}</span>}
        </div>
      )}
        <div>
          <h2 className="text-base font-semibold text-foreground">POP Translation</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Translate agricultural POP PDFs to English using Gemini
          </p>
        </div>

        <div className="flex flex-col gap-3">
          {/* State */}
          <div className="flex flex-col gap-1">
            <label className={labelClass}>State</label>
            <StateSelector
              value={state}
              onChange={setState}
              stateNames={stateOptions}
            />
          </div>

          {/* Crop */}
          <div className="flex flex-col gap-1">
            <label className={labelClass}>Crop</label>
            <select
              className={inputClass}
              value={crop}
              onChange={(e) => setCrop(e.target.value)}
              disabled={!state || cropOptions.length === 0}
            >
              <option value="">
                {!state ? 'Select a state first' : cropOptions.length === 0 ? 'No crops found' : '— select crop —'}
              </option>
              {cropOptions.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          {/* Docs */}
          <div className="flex flex-col gap-1">
            <label className={labelClass}>Documents <span className="font-normal text-muted-foreground">(leave empty to translate all)</span></label>
            <MultiSelector
              value={docs}
              onChange={setDocs}
              names={docOptions}
              placeholder={!crop ? 'Select a crop first' : docOptions.length === 0 ? 'No PDFs found' : 'Select documents…'}
            />
          </div>

          {/* Concurrency */}
          <div className="flex flex-col gap-1">
            <label className={labelClass}>Parallel pages (concurrency)</label>
            <input
              type="number"
              className={inputClass}
              min={1}
              max={10}
              value={concurrency}
              onChange={(e) => setConcurrency(Math.max(1, Math.min(10, parseInt(e.target.value) || 1)))}
            />
          </div>
        </div>

        <button
          className="mt-1 w-full py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium
            hover:bg-primary/90 active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          onClick={handleRun}
          disabled={!state || !crop || submitting || isRunning}
        >
          {submitting ? 'Submitting…' : isRunning ? 'Running…' : 'Run Translation'}
        </button>
      </div>
      </div>
      </div>
      <div className={`sticky top-0 z-10 bg-background pt-6 h-screen ${stacked ? 'overflow-y-auto' : 'overflow-hidden'}`}>
        <div className="max-w-4xl mx-auto w-full">
          <PopStateTable refreshKey={tableRefreshKey} />
        </div>
      </div>
    </div>
  );
}
