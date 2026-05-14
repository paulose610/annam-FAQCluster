import { useRef } from 'react';
import { Upload } from 'lucide-react';
import FileGroup from './FileGroup.jsx';
import { uploadFile } from '../../api.js';

export default function FilesPanel({ fileTree, onRefresh }) {
  const inputRef = useRef(null);

  function handleUploadClick() {
    inputRef.current.click();
  }

  function handleFileChange(e) {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    uploadFile(formData)
      .then(() => {
        onRefresh();
        e.target.value = '';
      })
      .catch((err) => {
        console.error('Upload failed:', err);
        e.target.value = '';
      });
  }

  return (
    <div className="flex flex-col h-full">
      <input
        ref={inputRef}
        type="file"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />
      <div className="p-2 border-b border-border">
        <button
          className="w-full flex items-center gap-2 px-3 py-2 border border-dashed border-border rounded-md text-sm text-muted-foreground bg-input hover:border-primary hover:bg-primary/5 hover:text-primary transition-colors"
          onClick={handleUploadClick}
        >
          <Upload size={14} />
          Upload file
        </button>
      </div>
      <FileGroup
        label="Input CSVs"
        files={fileTree.all_csvs || []}
        onDeleted={onRefresh}
        showPath
      />
      <FileGroup
        label="Crop QA Files"
        files={fileTree.crop_qa_files || []}
        onDeleted={onRefresh}
        groupBy="state"
      />
      <FileGroup
        label="Final CSVs"
        files={fileTree.final_csvs || []}
        onDeleted={onRefresh}
        groupBy="state"
      />
    </div>
  );
}
