import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import styles from './JobsPanel.module.css';

const STATUS_CARD_CLASS = {
  pending: styles.cardPending,
  running: styles.cardRunning,
  done: styles.cardDone,
  failed: styles.cardFailed,
};

const STATUS_DOT_CLASS = {
  pending: styles.dotPending,
  running: styles.dotRunning,
  done: styles.dotDone,
  failed: styles.dotFailed,
};

function formatLocalTime(isoString) {
  const d = new Date(isoString);
  return d.toLocaleString();
}

export default function JobCard({ job, onDelete, isExpanded, onToggle }) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  const canDelete = job.status === 'done' || job.status === 'failed';

  function handleCardClick(e) {
    onToggle();
  }

  function handleDeleteClick(e) {
    e.stopPropagation();
    if (confirmDelete) {
      onDelete(job.job_id);
    } else {
      setConfirmDelete(true);
    }
  }

  return (
    <div
      className={`${styles.card} ${STATUS_CARD_CLASS[job.status] || styles.cardPending}`}
      onClick={handleCardClick}
    >
      <div className={styles.cardHeader}>
        <div className={styles.statusRow}>
          <span className={`${styles.statusDot} ${STATUS_DOT_CLASS[job.status] || styles.dotPending}`} />
          <span className={styles.statusLabel}>{job.status}</span>
        </div>
        {canDelete && (
          confirmDelete ? (
            <span
              className={styles.confirmText}
              onClick={handleDeleteClick}
            >
              Sure?
            </span>
          ) : (
            <button className={styles.deleteBtn} onClick={handleDeleteClick}>
              <Trash2 size={13} />
            </button>
          )
        )}
      </div>
      <div className={styles.cardMeta}>
        <span>ID: {job.job_id.slice(0, 8)}</span>
        <span>{formatLocalTime(job.created_at)}</span>
      </div>
      {isExpanded && (
        <div className={styles.drawer} onClick={(e) => e.stopPropagation()}>
          <div className={styles.drawerLabel}>stdout</div>
          <div className={styles.stdout}>{job.stdout || '(empty)'}</div>
          {job.status === 'failed' && (
            <>
              <div className={styles.drawerLabel} style={{ marginTop: 8 }}>stderr</div>
              <div className={styles.stderr}>{job.stderr || '(empty)'}</div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
