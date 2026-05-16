import { useRef, useState } from 'react';
import { Download, MoreHorizontal } from 'lucide-react';
import { downloadUrl, deleteFile, renameFile } from '../../api.js';

export default function FileRow({
  file,
  onDeleted,
  depth = 0,
  pickMode,
  onPick,
  selectMode,
  selectedPaths,
  onToggleSelect,
  downloadUrlFn,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState('');
  const menuRef = useRef(null);

  const style = depth > 0 ? { paddingLeft: `${8 + depth * 18}px` } : { paddingLeft: '12px' };

  function handleDelete(e) {
    e.stopPropagation();
    setMenuOpen(false);
    deleteFile(file.path)
      .then(() => onDeleted())
      .catch((err) => console.error('Delete failed:', err));
  }

  function startRename(e) {
    e.stopPropagation();
    setMenuOpen(false);
    setNewName(file.name);
    setRenaming(true);
  }

  function commitRename() {
    const trimmed = newName.trim();
    if (!trimmed || trimmed === file.name) { setRenaming(false); return; }
    const parts = file.path.split('/');
    parts[parts.length - 1] = trimmed;
    const newPath = parts.join('/');
    renameFile(file.path, newPath)
      .then(() => { setRenaming(false); onDeleted(); })
      .catch((err) => { console.error('Rename failed:', err); setRenaming(false); });
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') commitRename();
    if (e.key === 'Escape') setRenaming(false);
  }

  function handleRowClick() {
    if (pickMode) { onPick(file.path); return; }
    if (selectMode) { onToggleSelect(file.path); }
  }

  const isSelected = selectMode && selectedPaths && selectedPaths.has(file.path);
  const isPickable = !!pickMode;

  return (
    <div
      className={`flex items-center gap-1 pr-1 py-1 text-xs text-muted-foreground transition-colors group
        ${isPickable ? 'cursor-pointer hover:bg-primary/10 hover:text-primary' : 'hover:bg-accent'}
        ${isSelected ? 'bg-primary/5' : ''}
      `}
      style={style}
      onClick={handleRowClick}
    >
      {selectMode && (
        <input
          type="checkbox"
          className="flex-shrink-0 w-3 h-3 rounded accent-primary cursor-pointer"
          checked={isSelected}
          onChange={() => onToggleSelect(file.path)}
          onClick={(e) => e.stopPropagation()}
        />
      )}

      {renaming ? (
        <input
          autoFocus
          type="text"
          className="flex-1 bg-input border border-ring rounded px-1 py-0 text-xs text-foreground outline-none"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onBlur={commitRename}
          onKeyDown={handleKeyDown}
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <span className="flex-1 truncate" title={file.path}>
          {file.displayName || file.name}
        </span>
      )}

      {!pickMode && !selectMode && (
        <>
          <a
            className="flex-shrink-0 w-6 h-6 flex items-center justify-center rounded text-muted-foreground/60 hover:bg-muted hover:text-foreground transition-colors opacity-0 group-hover:opacity-100"
            href={(downloadUrlFn ?? downloadUrl)(file.path)}
            download={file.name}
            onClick={(e) => e.stopPropagation()}
            title="Download"
          >
            <Download size={13} />
          </a>

          <div className="relative flex-shrink-0" ref={menuRef}>
            <button
              className="w-6 h-6 flex items-center justify-center rounded text-muted-foreground/60 hover:bg-muted hover:text-foreground transition-colors opacity-0 group-hover:opacity-100"
              onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v); }}
              title="More options"
            >
              <MoreHorizontal size={13} />
            </button>
            {menuOpen && (
              <div
                className="absolute right-0 top-full z-20 mt-0.5 w-28 bg-popover border border-border rounded-md shadow-lg py-1"
                onMouseLeave={() => setMenuOpen(false)}
              >
                <button
                  className="w-full text-left px-3 py-1.5 text-xs text-foreground hover:bg-accent"
                  onClick={startRename}
                >
                  Rename
                </button>
                <button
                  className="w-full text-left px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10"
                  onClick={handleDelete}
                >
                  Delete
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
