import { useState } from 'react';
import { RefreshCw, Trash2, Download, CheckSquare, Square, X } from 'lucide-react';
import FileGroup from './FileGroup.jsx';
import { uploadFile, uploadPopFile, deleteFile, downloadUrl, createFolder, createPopFolder, popDownloadUrl, deletePopFile, deletePopFolder } from '../../api.js';

export default function FilesPanel({ fileTree, onRefresh, pickMode, setPickMode, popDataFiles }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState(new Set());
  const [uploadProgress, setUploadProgress] = useState(null); // null | { pct: number, name: string }

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
    if (uploadProgress) return;
    setUploadProgress({ pct: 0, name: file.name });
    uploadFile(file, dest, (pct) => setUploadProgress({ pct, name: file.name }))
      .then(() => { setUploadProgress(null); handleRefresh(); })
      .catch((err) => { console.error('Upload failed:', err); setUploadProgress(null); });
  }

  function handleUploadPOP(file, dest = '') {
    if (uploadProgress) return;
    setUploadProgress({ pct: 0, name: file.name });
    uploadPopFile(file, dest, (pct) => setUploadProgress({ pct, name: file.name }))
      .then(() => { setUploadProgress(null); handleRefresh(); })
      .catch((err) => { console.error('POP upload failed:', err); setUploadProgress(null); });
  }

  function handleCreateFAQFolder(path) {
    createFolder(path)
      .then(handleRefresh)
      .catch((err) => console.error('Create folder failed:', err));
  }

  function handleCreatePopFolder(path) {
    createPopFolder(path)
      .then(handleRefresh)
      .catch((err) => console.error('Create folder failed:', err));
  }

  const isUploading = !!uploadProgress;

  const sharedProps = {
    onDeleted: handleRefresh,
    pickMode,
    onPick: handlePick,
    selectMode,
    selectedPaths,
    onToggleSelect: handleToggleSelect,
    refreshKey,
    isUploading,
  };

  const popSharedProps = {
    onDeleted: handleRefresh,
    pickMode: null,
    onPick: () => {},
    selectMode: false,
    selectedPaths: new Set(),
    onToggleSelect: () => {},
    refreshKey,
    downloadUrlFn: popDownloadUrl,
    isUploading,
    deleteFileFn: deletePopFile,
    deleteFolderFn: (path) => deletePopFolder(`Data/${path}`),
    noRename: true,
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

      {uploadProgress && (
        <div className="px-3 py-2 border-b border-border bg-muted/60">
          <div className="flex items-center justify-between mb-1 gap-2">
            <span className="text-xs text-foreground/70 truncate min-w-0">{uploadProgress.name}</span>
            <span className="text-xs text-muted-foreground flex-shrink-0">{uploadProgress.pct}%</span>
          </div>
          <div className="h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-150"
              style={{ width: `${uploadProgress.pct}%` }}
            />
          </div>
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
        accept=".csv"
        onCreateFolder={handleCreateFAQFolder}
        {...sharedProps}
      />
      <FileGroup
        label="Crop QA Files"
        files={fileTree.crop_qa_files || []}
        groupBy="state"
        basePath="outputs/repair"
        onCreateFolder={handleCreateFAQFolder}
        {...sharedProps}
      />
      <FileGroup
        label="Final CSVs"
        files={fileTree.final_csvs || []}
        groupBy="state"
        onCreateFolder={handleCreateFAQFolder}
        {...sharedProps}
      />
      <FileGroup
        label="POP Docs"
        files={popDataFiles || []}
        showPath
        onUpload={handleUploadPOP}
        accept=".pdf"
        onCreateFolder={handleCreatePopFolder}
        {...popSharedProps}
      />
    </div>
  );
}
