import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import styles from './JobsPanel.module.css';
import JobCard from './JobCard.jsx';

const FILTERS = ['all', 'running', 'done', 'failed'];

export default function JobsPanel({ jobs, onDeleteJob, onRefresh }) {
  const [activeFilter, setActiveFilter] = useState('all');
  const [expandedJobId, setExpandedJobId] = useState(null);

  const runningCount = jobs.filter((j) => j.status === 'running').length;
  const failedCount = jobs.filter((j) => j.status === 'failed').length;

  const filteredJobs =
    activeFilter === 'all' ? jobs : jobs.filter((j) => j.status === activeFilter);

  function handleToggle(jobId) {
    setExpandedJobId((prev) => (prev === jobId ? null : jobId));
  }

  return (
    <div className={styles.panel}>
      <div className={styles.tabs}>
        {FILTERS.map((f) => (
          <button
            key={f}
            className={`${styles.tab} ${activeFilter === f ? styles.tabActive : ''}`}
            onClick={() => setActiveFilter(f)}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
            {f === 'running' && runningCount > 0 && (
              <span className={`${styles.badge} ${styles.badgeBlue}`}>{runningCount}</span>
            )}
            {f === 'failed' && failedCount > 0 && (
              <span className={styles.badge}>{failedCount}</span>
            )}
          </button>
        ))}
        <button className={styles.refreshBtn} onClick={onRefresh} title="Refresh jobs">
          <RefreshCw size={13} />
        </button>
      </div>
      <div className={styles.jobList}>
        {filteredJobs.length === 0 && (
          <div className={styles.emptyMsg}>No jobs</div>
        )}
        {filteredJobs.map((job) => (
          <JobCard
            key={job.job_id}
            job={job}
            onDelete={onDeleteJob}
            isExpanded={expandedJobId === job.job_id}
            onToggle={() => handleToggle(job.job_id)}
          />
        ))}
      </div>
    </div>
  );
}
