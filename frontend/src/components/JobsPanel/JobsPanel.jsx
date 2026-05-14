import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import JobCard from './JobCard.jsx';

const FILTERS = ['all', 'running', 'done', 'failed', 'stopped'];

export default function JobsPanel({ jobs, onDeleteJob, onStopJob, onRefresh }) {
  const [activeFilter, setActiveFilter] = useState('all');
  const [expandedJobId, setExpandedJobId] = useState(null);

  const runningCount = jobs.filter((j) => j.status === 'running').length;
  const failedCount = jobs.filter((j) => j.status === 'failed').length;
  const stoppedCount = jobs.filter((j) => j.status === 'stopped').length;

  const filteredJobs =
    activeFilter === 'all' ? jobs : jobs.filter((j) => j.status === activeFilter);

  function handleToggle(jobId) {
    setExpandedJobId((prev) => (prev === jobId ? null : jobId));
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center border-b border-border bg-card flex-shrink-0 overflow-x-auto scrollbar-hide">
        {FILTERS.map((f) => (
          <button
            key={f}
            className={[
              'flex items-center gap-1 px-2.5 py-2.5 text-xs font-medium whitespace-nowrap transition-colors',
              activeFilter === f
                ? 'text-primary border-b-2 border-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-accent/50',
            ].join(' ')}
            onClick={() => setActiveFilter(f)}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
            {f === 'running' && runningCount > 0 && (
              <span className="rounded-full px-1.5 text-[10px] font-semibold bg-blue-500 text-white">
                {runningCount}
              </span>
            )}
            {f === 'failed' && failedCount > 0 && (
              <span className="rounded-full px-1.5 text-[10px] font-semibold bg-destructive text-white">
                {failedCount}
              </span>
            )}
            {f === 'stopped' && stoppedCount > 0 && (
              <span className="rounded-full px-1.5 text-[10px] font-semibold bg-amber-500 text-white">
                {stoppedCount}
              </span>
            )}
          </button>
        ))}
        <button
          className="ml-auto px-2 py-2.5 text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-colors flex-shrink-0"
          onClick={onRefresh}
          title="Refresh jobs"
        >
          <RefreshCw size={13} />
        </button>
      </div>
      <div className="flex flex-col gap-2 p-2 overflow-y-auto flex-1">
        {filteredJobs.length === 0 && (
          <div className="text-xs text-muted-foreground/60 text-center py-6 italic">No jobs</div>
        )}
        {filteredJobs.map((job) => (
          <JobCard
            key={job.job_id}
            job={job}
            onDelete={onDeleteJob}
            onStop={onStopJob}
            isExpanded={expandedJobId === job.job_id}
            onToggle={() => handleToggle(job.job_id)}
          />
        ))}
      </div>
    </div>
  );
}
