import { useState } from 'react';
import { toast } from 'sonner';

const inputClass =
  'w-full bg-input border border-border rounded-md px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-ring transition-shadow';

function CropsSelector({ value, onChange, cropNames }) {
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);

  const filtered = (cropNames || []).filter(
    (c) => !value.includes(c) && c.toLowerCase().includes(search.toLowerCase()),
  );

  function addCrop(crop) {
    onChange([...value, crop]);
    setSearch('');
  }

  function removeCrop(crop) {
    onChange(value.filter((c) => c !== crop));
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="relative">
        <input
          type="text"
          className={inputClass}
          placeholder="Search crops…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
        />
        {open && filtered.length > 0 && (
          <div className="absolute top-full left-0 right-0 z-10 mt-0.5 bg-popover border border-border rounded-md shadow-lg max-h-48 overflow-y-auto">
            {filtered.map((c) => (
              <button
                key={c}
                type="button"
                className="w-full text-left px-3 py-1.5 text-sm text-foreground hover:bg-accent hover:text-accent-foreground cursor-pointer"
                onMouseDown={() => addCrop(c)}
              >
                {c}
              </button>
            ))}
          </div>
        )}
      </div>
      {value.length > 0 && (
        <div className="flex flex-col gap-1 mt-1">
          {value.map((c) => (
            <div
              key={c}
              className="flex items-center justify-between bg-accent/40 border border-border rounded px-2 py-0.5 text-xs text-foreground"
            >
              <span>{c}</span>
              <button
                type="button"
                className="ml-2 text-muted-foreground hover:text-destructive leading-none cursor-pointer"
                onClick={() => removeCrop(c)}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function buildInitialValues(fields) {
  const vals = {};
  for (const f of fields) {
    if (f.type === 'crops-selector') {
      vals[f.key] = [];
    } else if (f.type === 'checkbox') {
      vals[f.key] = f.defaultValue !== undefined ? f.defaultValue : false;
    } else {
      vals[f.key] = f.defaultValue !== undefined ? f.defaultValue : '';
    }
  }
  return vals;
}

export default function RunTile({ title, description, fields, onRun, allCsvs, repairDirs, cropNames }) {
  const [values, setValues] = useState(() => buildInitialValues(fields));
  const [running, setRunning] = useState(false);

  function setValue(key, val) {
    setValues((prev) => ({ ...prev, [key]: val }));
  }

  async function handleRun() {
    const body = {};
    for (const f of fields) {
      const raw = values[f.key];
      if (f.type === 'checkbox') {
        body[f.key] = Boolean(raw);
      } else if (f.type === 'number') {
        if (raw !== '' && raw !== undefined && raw !== null) {
          body[f.key] = parseInt(raw, 10);
        }
      } else if (f.type === 'crops-selector') {
        if (raw.length > 0) {
          body[f.key] = raw;
        }
      } else {
        if (raw !== '' && raw !== undefined && raw !== null) {
          body[f.key] = raw;
        }
      }
    }

    setRunning(true);
    try {
      const result = await onRun(body);
      toast.success(`Job queued → ${result.job_id}`);
    } catch (err) {
      toast.error(err.message || 'Unknown error');
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="bg-card text-card-foreground rounded-lg border border-border shadow-sm p-4 flex flex-col gap-3">
      <div>
        <p className="text-sm font-bold text-foreground">{title}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
      </div>
      <div className="flex flex-col gap-2">
        {fields.map((f) => {
          if (f.type === 'checkbox') {
            return (
              <div key={f.key} className="flex items-center gap-2">
                <input
                  id={`${title}-${f.key}`}
                  type="checkbox"
                  className="w-4 h-4 rounded accent-primary cursor-pointer"
                  checked={Boolean(values[f.key])}
                  onChange={(e) => setValue(f.key, e.target.checked)}
                />
                <label
                  htmlFor={`${title}-${f.key}`}
                  className="text-xs font-medium text-muted-foreground cursor-pointer select-none"
                >
                  {f.label}
                </label>
              </div>
            );
          }
          if (f.type === 'select') {
            return (
              <div key={f.key} className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">{f.label}</label>
                <select
                  className={inputClass}
                  value={values[f.key]}
                  onChange={(e) => setValue(f.key, e.target.value)}
                >
                  {(f.options || []).map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            );
          }
          if (f.type === 'csv-dropdown') {
            return (
              <div key={f.key} className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">{f.label}</label>
                <select
                  className={inputClass}
                  value={values[f.key]}
                  onChange={(e) => setValue(f.key, e.target.value)}
                >
                  <option value="">-- select CSV --</option>
                  {(allCsvs || []).map((csv) => (
                    <option key={csv.path} value={csv.path}>
                      {csv.name}
                    </option>
                  ))}
                </select>
              </div>
            );
          }
          if (f.type === 'repair-dir-dropdown') {
            return (
              <div key={f.key} className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">{f.label}</label>
                <select
                  className={inputClass}
                  value={values[f.key]}
                  onChange={(e) => setValue(f.key, e.target.value)}
                >
                  <option value="">-- select folder --</option>
                  {(repairDirs || []).map((d) => (
                    <option key={d.path} value={d.path}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </div>
            );
          }
          if (f.type === 'crops-selector') {
            return (
              <div key={f.key} className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">{f.label}</label>
                <CropsSelector
                  value={values[f.key]}
                  onChange={(v) => setValue(f.key, v)}
                  cropNames={cropNames}
                />
              </div>
            );
          }
          return (
            <div key={f.key} className="flex flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">{f.label}</label>
              <input
                type={f.type}
                className={inputClass}
                value={values[f.key]}
                onChange={(e) => setValue(f.key, e.target.value)}
              />
            </div>
          );
        })}
      </div>
      <button
        className="w-full mt-auto bg-primary text-primary-foreground hover:bg-primary/90 active:scale-[0.98] rounded-md py-2 text-sm font-medium transition-all disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
        onClick={handleRun}
        disabled={running}
      >
        {running ? 'Running…' : 'Run'}
      </button>
    </div>
  );
}
