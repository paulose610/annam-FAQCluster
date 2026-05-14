import { Download, Trash2 } from 'lucide-react';
import { downloadUrl, deleteFile } from '../../api.js';

export default function FileRow({ file, onDeleted, depth = 0 }) {
  function handleDelete(e) {
    e.stopPropagation();
    deleteFile(file.path)
      .then(() => onDeleted())
      .catch((err) => console.error('Delete failed:', err));
  }

  const style = depth > 0 ? { paddingLeft: `${8 + depth * 14}px` } : { paddingLeft: '12px' };

  return (
    <div
      className="flex items-center gap-1 pr-1 py-1 text-xs text-muted-foreground hover:bg-accent transition-colors group"
      style={style}
    >
      <span className="flex-1 truncate" title={file.path}>
        {file.name}
      </span>
      <a
        className="flex-shrink-0 w-6 h-6 flex items-center justify-center rounded text-muted-foreground/60 hover:bg-muted hover:text-foreground transition-colors opacity-0 group-hover:opacity-100"
        href={downloadUrl(file.path)}
        download={file.name}
        onClick={(e) => e.stopPropagation()}
        title="Download"
      >
        <Download size={13} />
      </a>
      <button
        className="flex-shrink-0 w-6 h-6 flex items-center justify-center rounded text-muted-foreground/60 hover:bg-destructive/10 hover:text-destructive transition-colors opacity-0 group-hover:opacity-100"
        onClick={handleDelete}
        title="Delete"
      >
        <Trash2 size={13} />
      </button>
    </div>
  );
}
