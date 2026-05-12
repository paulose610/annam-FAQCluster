import { Download, Trash2 } from 'lucide-react';
import styles from './FilesPanel.module.css';
import { downloadUrl, deleteFile } from '../../api.js';

export default function FileRow({ file, onDeleted, depth = 0 }) {
  function handleDelete(e) {
    e.stopPropagation();
    deleteFile(file.path)
      .then(() => onDeleted())
      .catch((err) => console.error('Delete failed:', err));
  }

  const style = depth > 0 ? { paddingLeft: `${8 + depth * 14}px` } : {};

  return (
    <div className={styles.fileRow} style={style}>
      <span className={styles.fileName} title={file.path}>
        {file.name}
      </span>
      <a
        className={styles.iconBtn}
        href={downloadUrl(file.path)}
        download={file.name}
        onClick={(e) => e.stopPropagation()}
        title="Download"
      >
        <Download size={14} />
      </a>
      <button
        className={`${styles.iconBtn} ${styles.iconBtnDelete}`}
        onClick={handleDelete}
        title="Delete"
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}
