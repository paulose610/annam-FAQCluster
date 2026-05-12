import { useEffect, useState } from 'react';
import styles from './App.module.css';
import Header from './components/Header.jsx';
import FilesPanel from './components/FilesPanel/FilesPanel.jsx';
import FunctionsPanel from './components/FunctionsPanel/FunctionsPanel.jsx';
import JobsPanel from './components/JobsPanel/JobsPanel.jsx';
import { getTree, getJobs, deleteJob } from './api.js';

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

  function handleFileDeleted() {
    getTree()
      .then(setFileTree)
      .catch((err) => console.error('Failed to refresh file tree:', err));
  }

  return (
    <>
      <Header />
      <div className={styles.body}>
        <div className={styles.leftCol}>
          <FilesPanel fileTree={fileTree} onRefresh={handleFileDeleted} />
        </div>
        <div className={styles.centerCol}>
          <FunctionsPanel allCsvs={fileTree.all_csvs} />
        </div>
        <div className={styles.rightCol}>
          <JobsPanel jobs={jobs} onDeleteJob={handleDeleteJob} onRefresh={handleRefreshJobs} />
        </div>
      </div>
    </>
  );
}
