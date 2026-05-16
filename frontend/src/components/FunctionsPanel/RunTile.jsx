import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { toast } from 'sonner';

const inputClass =
  'w-full bg-input border border-border rounded-md px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-ring transition-shadow';

function MultiSelector({ value, onChange, names, placeholder }) {
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [expanded, setExpanded] = useState(false);
  const [expandedRect, setExpandedRect] = useState(null);
  const listRef = useRef(null);
  const containerRef = useRef(null);

  const filtered = (names || []).filter(
    (c) => !value.includes(c) && c.toLowerCase().includes(search.trim().toLowerCase()),
  );

  useEffect(() => {
    if (listRef.current && highlightedIndex >= 0) {
      const item = listRef.current.children[highlightedIndex];
      if (item) item.scrollIntoView({ block: 'nearest' });
    }
  }, [highlightedIndex]);

  function addItem(item) {
    onChange([...value, item]);
    setSearch('');
    setHighlightedIndex(-1);
  }

  function removeItem(item) {
    onChange(value.filter((c) => c !== item));
  }

  function handleKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setHighlightedIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (highlightedIndex >= 0 && highlightedIndex < filtered.length) {
        addItem(filtered[highlightedIndex]);
      }
    } else if (e.key === 'Escape') {
      if (expanded) setExpanded(false);
      else { setOpen(false); setHighlightedIndex(-1); }
    }
  }

  function handleExpand(e) {
    e.preventDefault();
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setExpandedRect({ left: rect.left, width: rect.width });
    }
    setExpanded(true);
  }

  const listItems = filtered.map((c, i) => (
    <button
      key={c}
      type="button"
      className={`w-full text-left px-3 py-1.5 text-sm cursor-pointer ${i === highlightedIndex ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-accent hover:text-accent-foreground'}`}
      onMouseDown={() => addItem(c)}
      onMouseEnter={() => setHighlightedIndex(i)}
    >
      {c}
    </button>
  ));

  return (
    <div className="flex flex-col gap-1">
      <div className="relative" ref={containerRef}>
        <input
          type="text"
          className={inputClass}
          placeholder={placeholder}
          value={search}
          onChange={(e) => { setSearch(e.target.value); setOpen(true); setHighlightedIndex(-1); }}
          onFocus={() => setOpen(true)}
          onBlur={() => { if (!expanded) setTimeout(() => { setOpen(false); setHighlightedIndex(-1); }, 150); }}
          onKeyDown={handleKeyDown}
        />
        {open && filtered.length > 0 && !expanded && (
          <div className="absolute top-full left-0 right-0 z-10 mt-0.5 bg-popover border border-border rounded-md shadow-lg">
            <div className="flex justify-end px-1 py-0.5 border-b border-border/40">
              <button
                type="button"
                title="Expand"
                className="text-muted-foreground hover:text-foreground px-1.5 py-0.5 rounded hover:bg-accent cursor-pointer text-xs leading-none"
                onMouseDown={handleExpand}
              >
                ↕
              </button>
            </div>
            <div ref={listRef} className="max-h-44 overflow-y-auto">
              {listItems}
            </div>
          </div>
        )}
      </div>
      {expanded && open && filtered.length > 0 && createPortal(
        <div
          style={{
            position: 'fixed',
            top: 0,
            bottom: 0,
            left: expandedRect?.left ?? 0,
            width: expandedRect?.width ?? 300,
            zIndex: 9999,
          }}
          className="bg-popover border border-border rounded-md shadow-xl flex flex-col"
        >
          <div className="flex justify-end px-1 py-0.5 border-b border-border/40 shrink-0">
            <button
              type="button"
              title="Collapse"
              className="text-muted-foreground hover:text-foreground px-1.5 py-0.5 rounded hover:bg-accent cursor-pointer text-base leading-none"
              onClick={() => setExpanded(false)}
            >
              ×
            </button>
          </div>
          <div ref={listRef} className="flex-1 overflow-y-auto">
            {listItems}
          </div>
        </div>,
        document.body,
      )}
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
                onClick={() => removeItem(c)}
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

function StateSelector({ value, onChange, stateNames }) {
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [expanded, setExpanded] = useState(false);
  const [expandedRect, setExpandedRect] = useState(null);
  const listRef = useRef(null);
  const containerRef = useRef(null);

  const displayText = value || search;
  const filtered = (stateNames || []).filter(
    (s) => s.toLowerCase().includes((value ? '' : search).toLowerCase()),
  );

  useEffect(() => {
    if (listRef.current && highlightedIndex >= 0) {
      const item = listRef.current.children[highlightedIndex];
      if (item) item.scrollIntoView({ block: 'nearest' });
    }
  }, [highlightedIndex]);

  function selectState(state) {
    onChange(state);
    setSearch('');
    setOpen(false);
    setExpanded(false);
    setHighlightedIndex(-1);
  }

  function handleInput(e) {
    onChange('');
    setSearch(e.target.value);
    setOpen(true);
    setHighlightedIndex(-1);
  }

  function handleClear(e) {
    e.preventDefault();
    onChange('');
    setSearch('');
    setHighlightedIndex(-1);
  }

  function handleKeyDown(e) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setHighlightedIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (highlightedIndex >= 0 && highlightedIndex < filtered.length) {
        selectState(filtered[highlightedIndex]);
      }
    } else if (e.key === 'Escape') {
      if (expanded) setExpanded(false);
      else { setOpen(false); setHighlightedIndex(-1); }
    }
  }

  function handleExpand(e) {
    e.preventDefault();
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setExpandedRect({ left: rect.left, width: rect.width });
    }
    setExpanded(true);
  }

  const listItems = filtered.map((s, i) => (
    <button
      key={s}
      type="button"
      className={`w-full text-left px-3 py-1.5 text-sm cursor-pointer ${i === highlightedIndex ? 'bg-accent text-accent-foreground' : 'text-foreground hover:bg-accent hover:text-accent-foreground'}`}
      onMouseDown={() => selectState(s)}
      onMouseEnter={() => setHighlightedIndex(i)}
    >
      {s}
    </button>
  ));

  return (
    <div className="flex flex-col gap-1">
      <div className="relative" ref={containerRef}>
        <input
          type="text"
          className={inputClass}
          placeholder="Search state…"
          value={displayText}
          onChange={handleInput}
          onFocus={() => setOpen(true)}
          onBlur={() => { if (!expanded) setTimeout(() => { setOpen(false); setHighlightedIndex(-1); }, 150); }}
          onKeyDown={handleKeyDown}
        />
        {value && (
          <button
            type="button"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-destructive leading-none cursor-pointer"
            onMouseDown={handleClear}
          >
            ×
          </button>
        )}
        {open && filtered.length > 0 && !expanded && (
          <div className="absolute top-full left-0 right-0 z-10 mt-0.5 bg-popover border border-border rounded-md shadow-lg">
            <div className="flex justify-end px-1 py-0.5 border-b border-border/40">
              <button
                type="button"
                title="Expand"
                className="text-muted-foreground hover:text-foreground px-1.5 py-0.5 rounded hover:bg-accent cursor-pointer text-xs leading-none"
                onMouseDown={handleExpand}
              >
                ↕
              </button>
            </div>
            <div ref={listRef} className="max-h-44 overflow-y-auto">
              {listItems}
            </div>
          </div>
        )}
      </div>
      {expanded && open && filtered.length > 0 && createPortal(
        <div
          style={{
            position: 'fixed',
            top: 0,
            bottom: 0,
            left: expandedRect?.left ?? 0,
            width: expandedRect?.width ?? 300,
            zIndex: 9999,
          }}
          className="bg-popover border border-border rounded-md shadow-xl flex flex-col"
        >
          <div className="flex justify-end px-1 py-0.5 border-b border-border/40 shrink-0">
            <button
              type="button"
              title="Collapse"
              className="text-muted-foreground hover:text-foreground px-1.5 py-0.5 rounded hover:bg-accent cursor-pointer text-base leading-none"
              onClick={() => setExpanded(false)}
            >
              ×
            </button>
          </div>
          <div ref={listRef} className="flex-1 overflow-y-auto">
            {listItems}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}

function buildInitialValues(fields) {
  const vals = {};
  for (const f of fields) {
    if (f.type === 'crops-selector' || f.type === 'domains-selector') {
      vals[f.key] = [];
    } else if (f.type === 'states-selector') {
      vals[f.key] = '';
    } else if (f.type === 'checkbox') {
      vals[f.key] = f.defaultValue !== undefined ? f.defaultValue : false;
    } else {
      vals[f.key] = f.defaultValue !== undefined ? f.defaultValue : '';
    }
  }
  return vals;
}

export default function RunTile({ title, description, fields, onRun, allCsvs, repairDirs, cropNames, domainNames, stateNames, onRequestPick }) {
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
      } else if (f.type === 'crops-selector' || f.type === 'domains-selector') {
        if (raw.length > 0) {
          body[f.key] = raw;
        }
      } else if (f.type === 'states-selector') {
        if (raw) {
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
          if (f.type === 'csv-from-sidebar') {
            return (
              <div key={f.key} className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">{f.label}</label>
                <div className="flex gap-1">
                  <input
                    readOnly
                    type="text"
                    className={`${inputClass} flex-1 cursor-default`}
                    value={values[f.key]}
                    placeholder="Browse sidebar…"
                  />
                  <button
                    type="button"
                    className="flex-shrink-0 px-2 py-1.5 text-xs bg-accent text-foreground border border-border rounded-md hover:bg-accent/80 transition-colors"
                    onClick={() => onRequestPick && onRequestPick((path) => setValue(f.key, path))}
                  >
                    Browse
                  </button>
                </div>
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
                <MultiSelector
                  value={values[f.key]}
                  onChange={(v) => setValue(f.key, v)}
                  names={cropNames}
                  placeholder="Search crops…"
                />
                {f.hint && <p className="text-xs text-muted-foreground/70 italic">{f.hint}</p>}
              </div>
            );
          }
          if (f.type === 'domains-selector') {
            return (
              <div key={f.key} className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">{f.label}</label>
                <MultiSelector
                  value={values[f.key]}
                  onChange={(v) => setValue(f.key, v)}
                  names={domainNames}
                  placeholder="Search domains…"
                />
                {f.hint && <p className="text-xs text-muted-foreground/70 italic">{f.hint}</p>}
              </div>
            );
          }
          if (f.type === 'states-selector') {
            return (
              <div key={f.key} className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">{f.label}</label>
                <StateSelector
                  value={values[f.key]}
                  onChange={(v) => setValue(f.key, v)}
                  stateNames={stateNames}
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
              {f.hint && <p className="text-xs text-muted-foreground/70 italic">{f.hint}</p>}
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
