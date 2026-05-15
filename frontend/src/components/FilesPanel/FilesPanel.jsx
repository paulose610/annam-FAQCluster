import { useRef, useState } from 'react';
import { RefreshCw, Upload, Trash2, Download, CheckSquare, Square, X } from 'lucide-react';
import FileGroup from './FileGroup.jsx';
import { uploadFile, deleteFile, downloadUrl } from '../../api.js';

export default function FilesPanel({ fileTree, onRefresh, pickMode, setPickMode }) {
  const inputRef = useRef(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState(new Set());

  function handleRefresh() {
    setRefreshKey((k) => k + 1);
    onRefresh();
  }

  function handleUploadClick() {
    inputRef.current.click();
  }

  function handleFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    uploadFile(formData)
      .then(() => { handleRefresh(); e.target.value = ''; })
      .catch((err) => { console.error('Upload failed:', err); e.target.value = ''; });
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

  const sharedProps = {
    onDeleted: handleRefresh,
    pickMode,
    onPick: handlePick,
    selectMode,
    selectedPaths,
    onToggleSelect: handleToggleSelect,
    refreshKey,
  };

  return (
    <div className="flex flex-col h-full">
      <input ref={inputRef} type="file" style={{ display: 'none' }} onChange={handleFileChange} />

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

      <div className="p-2 border-b border-border flex items-center gap-1">
        <button
          className="flex-1 flex items-center gap-2 px-3 py-2 border border-dashed border-border rounded-md text-sm text-muted-foreground bg-input hover:border-primary hover:bg-primary/5 hover:text-primary transition-colors"
          onClick={handleUploadClick}
        >
          <Upload size={14} />
          Upload file
        </button>
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

      <FileGroup label="Input CSVs" files={fileTree.all_csvs || []} showPath {...sharedProps} />
      <FileGroup
        label="Crop QA Files"
        files={fileTree.crop_qa_files || []}
        groupBy="state"
        basePath="outputs/repair"
        {...sharedProps}
      />
      <FileGroup
        label="Final CSVs"
        files={fileTree.final_csvs || []}
        groupBy="state"
        {...sharedProps}
      />
    </div>
  );
}
