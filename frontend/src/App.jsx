import { useEffect, useState } from 'react';
import { Toaster } from 'sonner';
import Header from './components/Header.jsx';
import FilesPanel from './components/FilesPanel/FilesPanel.jsx';
import FunctionsPanel from './components/FunctionsPanel/FunctionsPanel.jsx';
import PopTranslationPanel from './components/FunctionsPanel/PopTranslationPanel.jsx';
import JobsPanel from './components/JobsPanel/JobsPanel.jsx';
import { getAppTree, getJobs, deleteJob, stopJob } from './api.js';

const _EMPTY_TREE = { all_csvs: [], crop_qa_files: [], final_csvs: [], pop_files: [] };

export default function App() {
  const [appTree, setAppTree] = useState(_EMPTY_TREE);
  const [jobs, setJobs] = useState([]);
  const [pickMode, setPickMode] = useState(null);
  const [activeTab, setActiveTab] = useState('faq-cluster');

  function handleRefresh() {
    getAppTree()
      .then(setAppTree)
      .catch((err) => console.error('Failed to load tree:', err));
  }

  useEffect(() => {
    handleRefresh();
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

  const repairDirs = [...new Set((appTree.crop_qa_files || []).map((f) => f.state))]
    .sort()
    .map((s) => ({ name: s, path: `outputs/repair/${s}` }));

  const TABS = [
    { id: 'faq-cluster', label: 'FAQ-Cluster' },
    { id: 'pop-translation', label: 'POP-Translation' },
    { id: 'outreach', label: 'Outreach' },
  ];

  return (
    <div className="flex flex-col h-screen">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <div className={`w-60 flex-shrink-0 overflow-y-auto border-r border-border bg-card scrollbar-hide${pickMode ? ' ring-2 ring-primary' : ''}`}>
          <FilesPanel
            fileTree={appTree}
            onRefresh={handleRefresh}
            pickMode={pickMode}
            setPickMode={setPickMode}
            popDataFiles={appTree.pop_files || []}
          />
        </div>
        <div className="flex-1 overflow-y-auto bg-background flex flex-col">
          {/* Centered nav bar */}
          <div className="flex justify-center gap-1 border-b border-border px-4 py-2.5 flex-shrink-0">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors
                  ${activeTab === tab.id
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                  }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto p-4">
            {activeTab === 'faq-cluster' && (
              <FunctionsPanel
                repairDirs={repairDirs}
                onRequestPick={(onPick) => setPickMode({ onPick })}
              />
            )}
            {activeTab === 'pop-translation' && (
              <PopTranslationPanel onJobCreated={handleRefreshJobs} />
            )}
            {activeTab === 'outreach' && (
              <div className="flex items-center justify-center h-40">
                <p className="text-muted-foreground text-sm italic">Coming soon</p>
              </div>
            )}
          </div>
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
