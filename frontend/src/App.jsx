import { useEffect, useState } from 'react';
import { Toaster } from 'sonner';
import Header from './components/Header.jsx';
import FilesPanel from './components/FilesPanel/FilesPanel.jsx';
import FunctionsPanel from './components/FunctionsPanel/FunctionsPanel.jsx';
import JobsPanel from './components/JobsPanel/JobsPanel.jsx';
import { getTree, getJobs, deleteJob, stopJob } from './api.js';

export default function App() {
  const [fileTree, setFileTree] = useState({ all_csvs: [], crop_qa_files: [], final_csvs: [] });
  const [jobs, setJobs] = useState([]);

  useEffect(() => {
    getTree()
      .then(setFileTree)
      .catch((err) => console.error('Failed to load file tree:', err));
  }, []);

  function handleRefreshJobs() {
    getJobs()
      .then(setJobs)
      .catch((err) => console.error('Failed to refresh jobs:', err));
  }

  useEffect(() => {
    handleRefreshJobs();
    const id = setInterval(handleRefreshJobs, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  function handleDeleteJob(jobId) {
    deleteJob(jobId)
      .then(() => setJobs((prev) => prev.filter((j) => j.job_id !== jobId)))
      .catch((err) => console.error('Failed to delete job:', err));
  }

  function handleStopJob(jobId) {
    stopJob(jobId)
      .then(() =>
        setJobs((prev) =>
          prev.map((j) => (j.job_id === jobId ? { ...j, status: 'stopped' } : j))
        )
      )
      .catch((err) => console.error('Failed to stop job:', err));
  }

  function handleFileDeleted() {
    getTree()
      .then(setFileTree)
      .catch((err) => console.error('Failed to refresh file tree:', err));
  }

  const repairDirs = [...new Set((fileTree.crop_qa_files || []).map((f) => f.state))]
    .sort()
    .map((s) => ({ name: s, path: `outputs/repair/${s}` }));

  return (
    <div className="flex flex-col h-screen">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <div className="w-60 flex-shrink-0 overflow-y-auto border-r border-border bg-card scrollbar-hide">
          <FilesPanel fileTree={fileTree} onRefresh={handleFileDeleted} />
        </div>
        <div className="flex-1 overflow-y-auto p-4 bg-background">
          <FunctionsPanel allCsvs={fileTree.all_csvs} repairDirs={repairDirs} />
        </div>
        <div className="w-80 flex-shrink-0 overflow-y-auto border-l border-border bg-card scrollbar-hide">
          <JobsPanel
            jobs={jobs}
            onDeleteJob={handleDeleteJob}
            onStopJob={handleStopJob}
            onRefresh={handleRefreshJobs}
          />
        </div>
      </div>
      <Toaster richColors position="bottom-right" />
    </div>
  );
}
