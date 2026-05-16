import { useState } from 'react';
import { RefreshCw, Trash2, Download, CheckSquare, Square, X } from 'lucide-react';
import FileGroup from './FileGroup.jsx';
import { uploadFile, uploadPopFile, deleteFile, downloadUrl, createPopFolder, popDownloadUrl } from '../../api.js';

export default function FilesPanel({ fileTree, onRefresh, pickMode, setPickMode, popDataFiles, onPopRefresh }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState(new Set());

  function handleRefresh() {
    setRefreshKey((k) => k + 1);
    onRefresh();
  }

  function toggleSelectMode() {
    setSelectMode((v) => !v);
    setSelectedPaths(new Set());
  }

  function handleToggleSelect(path) {
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  function handleBatchDownload() {
    if (selectedPaths.size === 0) return;
    [...selectedPaths].forEach((p) => {
      const a = document.createElement('a');
      a.href = downloadUrl(p);
      a.download = p.split('/').pop();
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    });
  }

  async function handleBatchDelete() {
    if (selectedPaths.size === 0) return;
    if (!window.confirm(`Delete ${selectedPaths.size} selected file(s)?`)) return;
    await Promise.all([...selectedPaths].map((p) => deleteFile(p).catch(() => {})));
    setSelectedPaths(new Set());
    setSelectMode(false);
    handleRefresh();
  }

  function handlePick(path) {
    if (pickMode) {
      pickMode.onPick(path);
      setPickMode(null);
    }
  }

  function handleUploadFAQ(file, dest = '') {
    const fd = new FormData();
    fd.append('file', file);
    uploadFile(fd, dest)
      .then(handleRefresh)
      .catch((err) => console.error('Upload failed:', err));
  }

  function handleUploadPOP(file, dest = '') {
    const fd = new FormData();
    fd.append('file', file);
    uploadPopFile(fd, dest)
      .then(() => { if (onPopRefresh) onPopRefresh(); })
      .catch((err) => console.error('POP upload failed:', err));
  }

  function handleCreatePopFolder(path) {
    createPopFolder(path)
      .then(() => { if (onPopRefresh) onPopRefresh(); })
      .catch((err) => console.error('Create folder failed:', err));
  }

  const sharedProps = {
    onDeleted: handleRefresh,
    pickMode,
    onPick: handlePick,
    selectMode,
    selectedPaths,
    onToggleSelect: handleToggleSelect,
    refreshKey,
  };

  const popSharedProps = {
    onDeleted: onPopRefresh || handleRefresh,
    pickMode: null,
    onPick: () => {},
    selectMode: false,
    selectedPaths: new Set(),
    onToggleSelect: () => {},
    refreshKey,
    downloadUrlFn: popDownloadUrl,
  };

  return (
    <div className="flex flex-col h-full">
      {/* Pick-mode banner */}
      {pickMode && (
        <div className="flex items-center justify-between px-3 py-1.5 bg-primary/10 border-b border-primary/30 text-xs text-primary font-medium">
          <span>Click a file to select</span>
          <button
            className="w-5 h-5 flex items-center justify-center rounded hover:bg-primary/20"
            onClick={() => setPickMode(null)}
            title="Cancel"
          >
            <X size={12} />
          </button>
        </div>
      )}

      <div className="p-2 border-b border-border flex items-center justify-end gap-1">
        <button
          className={`flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-md transition-colors ${selectMode ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent hover:text-foreground'}`}
          onClick={toggleSelectMode}
          title={selectMode ? 'Exit selection mode' : 'Select files'}
        >
          {selectMode ? <CheckSquare size={13} /> : <Square size={13} />}
        </button>
        {selectMode && (
          <>
            <button
              className={`flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-md transition-colors ${selectedPaths.size > 0 ? 'text-primary hover:bg-primary/10' : 'text-muted-foreground/40 cursor-not-allowed'}`}
              onClick={handleBatchDownload}
              disabled={selectedPaths.size === 0}
              title={`Download ${selectedPaths.size} selected`}
            >
              <Download size={13} />
            </button>
            <button
              className={`flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-md transition-colors ${selectedPaths.size > 0 ? 'text-destructive hover:bg-destructive/10' : 'text-muted-foreground/40 cursor-not-allowed'}`}
              onClick={handleBatchDelete}
              disabled={selectedPaths.size === 0}
              title={`Delete ${selectedPaths.size} selected`}
            >
              <Trash2 size={13} />
            </button>
          </>
        )}
        <button
          className="flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          onClick={handleRefresh}
          title="Refresh files"
        >
          <RefreshCw size={13} />
        </button>
      </div>

      <FileGroup
        label="Input CSVs"
        files={fileTree.all_csvs || []}
        showPath
        onUpload={handleUploadFAQ}
        {...sharedProps}
      />
      <FileGroup
        label="Crop QA Files"
        files={fileTree.crop_qa_files || []}
        groupBy="state"
        basePath="outputs/repair"
        onUpload={handleUploadFAQ}
        {...sharedProps}
      />
      <FileGroup
        label="Final CSVs"
        files={fileTree.final_csvs || []}
        groupBy="state"
        onUpload={handleUploadFAQ}
        {...sharedProps}
      />
      <FileGroup
        label="POP Docs"
        files={popDataFiles || []}
        showPath
        onUpload={handleUploadPOP}
        onCreateFolder={handleCreatePopFolder}
        {...popSharedProps}
      />
    </div>
  );
}
