import { useState } from 'react';
import { Trash2, Square } from 'lucide-react';
import PipelineOutput, { parsePipelineOutput, PostPipelineOutput, parsePostPipelineOutput, PrePipelineOutput, parsePrePipelineOutput } from './PipelineOutput.jsx';

const STATUS_BORDER = {
  pending: 'border-l-muted-foreground',
  running: 'border-l-blue-500',
  done: 'border-l-green-500',
  failed: 'border-l-destructive',
  stopped: 'border-l-amber-500',
};

const STATUS_DOT = {
  pending: 'bg-muted-foreground',
  running: 'bg-blue-500 animate-pulse',
  done: 'bg-green-500',
  failed: 'bg-destructive',
  stopped: 'bg-amber-500',
};

function formatLocalTime(isoString) {
  const d = new Date(isoString);
  return d.toLocaleString();
}

export default function JobCard({ job, onDelete, onStop, isExpanded, onToggle }) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  const canDelete = job.status === 'done' || job.status === 'failed' || job.status === 'stopped';
  const canStop = job.status === 'running';

  function handleDeleteClick(e) {
    e.stopPropagation();
    if (confirmDelete) {
      onDelete(job.job_id);
    } else {
      setConfirmDelete(true);
    }
  }

  function handleStopClick(e) {
    e.stopPropagation();
    onStop(job.job_id);
  }

  const typeLabel = job.job_type_id != null
    ? `#${job.job_type_id} ${job.job_type ?? ''}`
    : null;

  const borderColor = STATUS_BORDER[job.status] || STATUS_BORDER.pending;

  return (
    <div
      className={`bg-card rounded-lg border border-border border-l-4 ${borderColor} shadow-sm cursor-pointer hover:shadow-md transition-shadow`}
      onClick={onToggle}
    >
      <div className="flex items-center justify-between px-3 pt-2.5 pb-1">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOT[job.status] || STATUS_DOT.pending}`} />
          <span className="text-xs font-medium text-foreground capitalize">{job.status}</span>
        </div>
        <div className="flex items-center gap-1">
          {canStop && (
            <button
              className="flex items-center gap-1 px-2 py-0.5 rounded border border-destructive/40 text-destructive hover:bg-destructive/10 text-xs transition-colors"
              onClick={handleStopClick}
            >
              <Square size={11} />
              Stop
            </button>
          )}
          {canDelete && (
            confirmDelete ? (
              <span
                className="px-2 py-0.5 rounded border border-destructive/40 text-destructive hover:bg-destructive/10 text-xs cursor-pointer transition-colors"
                onClick={handleDeleteClick}
              >
                Sure?
              </span>
            ) : (
              <button
                className="w-6 h-6 flex items-center justify-center rounded border border-border text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                onClick={handleDeleteClick}
              >
                <Trash2 size={13} />
              </button>
            )
          )}
        </div>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 px-3 pb-2.5 text-[11px] text-muted-foreground">
        {typeLabel && <span>{typeLabel}</span>}
        <span>ID: {job.job_id.slice(0, 8)}</span>
        <span>{formatLocalTime(job.created_at)}</span>
      </div>
      {isExpanded && (
        <div className="border-t border-border px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
          {parsePipelineOutput(job.stdout) ? (
            <PipelineOutput stdout={job.stdout} />
          ) : parsePostPipelineOutput(job.stdout) ? (
            <PostPipelineOutput stdout={job.stdout} />
          ) : parsePrePipelineOutput(job.stdout) ? (
            <PrePipelineOutput stdout={job.stdout} />
          ) : (
            <>
              <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">stdout</div>
              <pre className="font-mono text-xs bg-slate-900 text-slate-400 p-2 max-h-72 overflow-y-auto rounded whitespace-pre-wrap">{job.stdout || '(empty)'}</pre>
            </>
          )}
          {(job.status === 'failed' || job.status === 'stopped') && (
            <>
              <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1 mt-2">stderr</div>
              <pre className="font-mono text-xs bg-red-950 text-red-300 p-2 max-h-72 overflow-y-auto rounded whitespace-pre-wrap mt-1">{job.stderr || '(empty)'}</pre>
            </>
          )}
        </div>
      )}
    </div>
  );
}
