import { useState } from 'react';
import styles from './FunctionsPanel.module.css';

function buildInitialValues(fields) {
  const vals = {};
  for (const f of fields) {
    vals[f.key] = f.defaultValue !== undefined ? f.defaultValue : (f.type === 'checkbox' ? false : '');
  }
  return vals;
}

export default function RunTile({ title, description, fields, onRun, allCsvs }) {
  const [values, setValues] = useState(() => buildInitialValues(fields));
  const [running, setRunning] = useState(false);
  const [toast, setToast] = useState(null); // { message, isError }

  function setValue(key, val) {
    setValues((prev) => ({ ...prev, [key]: val }));
  }

  function showToast(message, isError = false) {
    setToast({ message, isError });
    setTimeout(() => setToast(null), 3000);
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
      } else if (f.type === 'crops') {
        const list = String(raw)
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
        if (list.length > 0) {
          body[f.key] = list;
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
      showToast(`Job queued → ${result.job_id}`);
    } catch (err) {
      showToast(err.message || 'Unknown error', true);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className={styles.tile}>
      <div className={styles.tileHeader}>
        <p className={styles.tileTitle}>{title}</p>
        <p className={styles.tileDesc}>{description}</p>
      </div>
      <div className={styles.fieldGroup}>
        {fields.map((f) => {
          if (f.type === 'checkbox') {
            return (
              <div key={f.key} className={styles.checkboxRow}>
                <input
                  id={`${title}-${f.key}`}
                  type="checkbox"
                  className={styles.checkbox}
                  checked={Boolean(values[f.key])}
                  onChange={(e) => setValue(f.key, e.target.checked)}
                />
                <label htmlFor={`${title}-${f.key}`} className={styles.label}>
                  {f.label}
                </label>
              </div>
            );
          }
          if (f.type === 'select') {
            return (
              <div key={f.key} className={styles.field}>
                <label className={styles.label}>{f.label}</label>
                <select
                  className={styles.select}
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
              <div key={f.key} className={styles.field}>
                <label className={styles.label}>{f.label}</label>
                <select
                  className={styles.select}
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
          return (
            <div key={f.key} className={styles.field}>
              <label className={styles.label}>{f.label}</label>
              <input
                type={f.type === 'crops' ? 'text' : f.type}
                className={styles.input}
                value={values[f.key]}
                placeholder={f.type === 'crops' ? 'comma-separated' : ''}
                onChange={(e) => setValue(f.key, e.target.value)}
              />
            </div>
          );
        })}
      </div>
      <button className={styles.runBtn} onClick={handleRun} disabled={running}>
        {running ? 'Running...' : 'Run'}
      </button>
      {toast && (
        <div className={`${styles.toast} ${toast.isError ? styles.toastError : ''}`}>
          {toast.message}
        </div>
      )}
    </div>
  );
}
