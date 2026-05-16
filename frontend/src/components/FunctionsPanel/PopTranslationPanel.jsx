import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { MultiSelector, StateSelector } from './RunTile.jsx';
import { getPopStates, getPopCrops, getPopDocs, runPop } from '../../api.js';

const inputClass =
  'w-full bg-input border border-border rounded-md px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-ring transition-shadow';

const labelClass = 'text-xs font-medium text-foreground/70';

export default function PopTranslationPanel({ onJobCreated }) {
  const [state, setState] = useState('');
  const [crop, setCrop] = useState('');
  const [docs, setDocs] = useState([]);
  const [concurrency, setConcurrency] = useState(1);
  const [running, setRunning] = useState(false);

  const [stateOptions, setStateOptions] = useState([]);
  const [cropOptions, setCropOptions] = useState([]);
  const [docOptions, setDocOptions] = useState([]);

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
    setRunning(true);
    try {
      const result = await runPop(body);
      toast.success(`POP job queued — ${result.job_id.slice(0, 8)}`);
      if (onJobCreated) onJobCreated();
    } catch (err) {
      toast.error(err.message || 'Failed to start POP translation');
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex justify-center">
      <div className="w-full max-w-md bg-card rounded-lg border border-border shadow-sm p-5 flex flex-col gap-4">
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
          disabled={!state || !crop || running}
        >
          {running ? 'Submitting…' : 'Run Translation'}
        </button>
      </div>
    </div>
  );
}
