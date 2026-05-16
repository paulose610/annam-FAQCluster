import { useRef, useState } from 'react';
import { ChevronDown, ChevronRight, Folder, MoreHorizontal } from 'lucide-react';
import FileRow from './FileRow.jsx';
import { deleteFolder, renameFile } from '../../api.js';

function FolderMenu({ path, name, onDeleted, node, folderKeys, forceConfirm = false, onUpload }) {
  const [open, setOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [newName, setNewName] = useState('');
  const fileInputRef = useRef(null);

  function handleDelete(e) {
    e.stopPropagation();
    setOpen(false);
    const nonEmpty = forceConfirm || (node?.files?.length > 0 || (folderKeys?.length ?? 0) > 0);
    if (nonEmpty && !window.confirm('This folder is not empty and will be deleted with all its contents. Continue?')) return;
    deleteFolder(path)
      .then(() => onDeleted())
      .catch((err) => console.error('Delete folder failed:', err));
  }

  function startRename(e) {
    e.stopPropagation();
    setOpen(false);
    setNewName(name);
    setRenaming(true);
  }

  function commitRename() {
    const trimmed = newName.trim();
    if (!trimmed || trimmed === name) { setRenaming(false); return; }
    const parts = path.split('/');
    parts[parts.length - 1] = trimmed;
    const newPath = parts.join('/');
    renameFile(path, newPath)
      .then(() => { setRenaming(false); onDeleted(); })
      .catch((err) => { console.error('Rename folder failed:', err); setRenaming(false); });
  }

  function handleUploadClick(e) {
    e.stopPropagation();
    setOpen(false);
    fileInputRef.current?.click();
  }

  function handleFileSelected(e) {
    const file = e.target.files[0];
    if (!file) return;
    onUpload?.(file);
    e.target.value = '';
  }

  if (renaming) {
    return (
      <input
        autoFocus
        type="text"
        className="flex-1 bg-input border border-ring rounded px-1 py-0 text-xs text-foreground outline-none"
        value={newName}
        onChange={(e) => setNewName(e.target.value)}
        onBlur={commitRename}
        onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setRenaming(false); }}
        onClick={(e) => e.stopPropagation()}
      />
    );
  }

  return (
    <div className="relative flex-shrink-0" onMouseLeave={() => setOpen(false)}>
      {onUpload && <input ref={fileInputRef} type="file" style={{ display: 'none' }} onChange={handleFileSelected} />}
      <button
        className="w-5 h-5 flex items-center justify-center rounded text-muted-foreground/60 hover:bg-muted hover:text-foreground transition-colors opacity-0 group-hover:opacity-100"
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        title="More options"
      >
        <MoreHorizontal size={11} />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-20 mt-0.5 w-32 bg-popover border border-border rounded-md shadow-lg py-1">
          {onUpload && (
            <button
              className="w-full text-left px-3 py-1.5 text-xs text-foreground hover:bg-accent"
              onClick={handleUploadClick}
            >
              Upload file
            </button>
          )}
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
  );
}

function buildTree(files) {
  const root = { folders: {}, files: [] };
  for (const file of files) {
    const displayPath = file.treePath || file.path;
    if (displayPath.split('/').includes('.ipynb_checkpoints')) continue;
    const parts = displayPath.split('/');
    let node = root;
    if (file.isDir) {
      for (const part of parts) {
        if (!node.folders[part]) node.folders[part] = { folders: {}, files: [] };
        node = node.folders[part];
      }
    } else {
      for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i];
        if (!node.folders[part]) node.folders[part] = { folders: {}, files: [] };
        node = node.folders[part];
      }
      node.files.push(file);
    }
  }
  return root;
}

function TreeNode({ name, node, depth, path, onDeleted, pickMode, onPick, selectMode, selectedPaths, onToggleSelect, downloadUrlFn, onUpload }) {
  const [open, setOpen] = useState(false);
  const isRoot = !name;
  const folderKeys = Object.keys(node.folders).sort();
  const indent = 8 + depth * 18;

  const rowProps = { onDeleted, pickMode, onPick, selectMode, selectedPaths, onToggleSelect, downloadUrlFn };

  return (
    <>
      {!isRoot && (
        <div
          className="flex items-center gap-1 py-1 text-xs text-muted-foreground cursor-pointer hover:bg-accent transition-colors group"
          style={{ paddingLeft: `${indent}px`, paddingRight: '4px' }}
          onClick={() => setOpen((v) => !v)}
        >
          <span className="text-muted-foreground/60 flex-shrink-0">
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>
          <Folder size={12} className="flex-shrink-0 text-muted-foreground/60" />
          <span className="truncate flex-1">{name}</span>
          <FolderMenu
            path={path}
            name={name}
            onDeleted={onDeleted}
            node={node}
            folderKeys={folderKeys}
            onUpload={onUpload ? (file) => onUpload(file, path) : undefined}
          />
        </div>
      )}
      {(isRoot || open) && (
        <>
          {folderKeys.map((k) => (
            <TreeNode
              key={k}
              name={k}
              node={node.folders[k]}
              depth={isRoot ? depth : depth + 1}
              path={path ? `${path}/${k}` : k}
              onUpload={onUpload}
              {...rowProps}
            />
          ))}
          {node.files.map((file) => (
            <FileRow
              key={file.path}
              file={file}
              depth={isRoot ? depth : depth + 1}
              {...rowProps}
            />
          ))}
        </>
      )}
    </>
  );
}

function SubGroup({ label, files, folderPath, onDeleted, pickMode, onPick, selectMode, selectedPaths, onToggleSelect, downloadUrlFn, onUpload }) {
  const [open, setOpen] = useState(false);

  const rowProps = { onDeleted, pickMode, onPick, selectMode, selectedPaths, onToggleSelect, downloadUrlFn };

  return (
    <>
      <div
        className="flex items-center gap-1 px-3 py-1 text-xs text-muted-foreground cursor-pointer hover:bg-accent transition-colors group"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-muted-foreground/60 flex-shrink-0">
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
        <Folder size={12} className="flex-shrink-0 text-muted-foreground/60" />
        <span className="truncate flex-1">{label}</span>
        <FolderMenu
          path={folderPath}
          name={label}
          onDeleted={onDeleted}
          forceConfirm={files.length > 0}
          onUpload={onUpload ? (file) => onUpload(file, folderPath) : undefined}
        />
      </div>
      {open &&
        files.map((file) => (
          <FileRow key={file.path} file={file} depth={1} {...rowProps} />
        ))}
    </>
  );
}

export default function FileGroup({
  label, files, onDeleted, groupBy, showPath = false, basePath, refreshKey,
  pickMode, onPick, selectMode, selectedPaths, onToggleSelect, downloadUrlFn,
  onUpload,
  onCreateFolder,
}) {
  const [open, setOpen] = useState(true);
  const [groupMenuOpen, setGroupMenuOpen] = useState(false);
  const [showFolderInput, setShowFolderInput] = useState(false);
  const [folderName, setFolderName] = useState('');
  const fileInputRef = useRef(null);

  const rowProps = { onDeleted, pickMode, onPick, selectMode, selectedPaths, onToggleSelect, downloadUrlFn };

  function handleGroupUploadClick(e) {
    e.stopPropagation();
    setGroupMenuOpen(false);
    fileInputRef.current?.click();
  }

  function handleGroupFileSelected(e) {
    const file = e.target.files[0];
    if (!file) return;
    onUpload?.(file, '');
    e.target.value = '';
  }

  function handleCreateFolderClick(e) {
    e.stopPropagation();
    setGroupMenuOpen(false);
    setShowFolderInput(true);
  }

  function commitFolder() {
    const trimmed = folderName.trim();
    if (trimmed) onCreateFolder?.(trimmed);
    setFolderName('');
    setShowFolderInput(false);
  }

  let content = null;
  if (open) {
    if (showPath) {
      if (files.length === 0) {
        content = <div className="px-4 py-2 text-xs text-muted-foreground/60 italic">No files</div>;
      } else {
        const tree = buildTree(files);
        content = <TreeNode key={refreshKey} name={null} node={tree} depth={0} path="" onUpload={onUpload} {...rowProps} />;
      }
    } else if (groupBy) {
      const groups = {};
      for (const file of files) {
        const key = file[groupBy] || '(unknown)';
        if (!groups[key]) groups[key] = [];
        groups[key].push(file);
      }
      const keys = Object.keys(groups).sort();
      if (keys.length === 0) {
        content = <div className="px-4 py-2 text-xs text-muted-foreground/60 italic">No files</div>;
      } else {
        content = keys.map((k) => {
          const fp = groups[k][0]?.folderPath || (basePath ? `${basePath}/${k}` : k);
          return (
            <SubGroup
              key={`${refreshKey}-${k}`}
              label={k}
              files={groups[k]}
              folderPath={fp}
              onUpload={onUpload}
              {...rowProps}
            />
          );
        });
      }
    } else {
      if (files.length === 0) {
        content = <div className="px-4 py-2 text-xs text-muted-foreground/60 italic">No files</div>;
      } else {
        content = files.map((file) => (
          <FileRow key={file.path} file={file} {...rowProps} />
        ));
      }
    }
  }

  return (
    <>
      <div
        className="flex items-center gap-1.5 px-3 py-2 cursor-pointer bg-muted hover:bg-accent transition-colors border-y border-border group"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-muted-foreground/60 flex-shrink-0">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <span className="text-xs font-semibold text-foreground/70 uppercase tracking-wider flex-1">{label}</span>
        {(onUpload || onCreateFolder) && (
          <div className="relative flex-shrink-0" onMouseLeave={() => setGroupMenuOpen(false)}>
            {onUpload && (
              <input ref={fileInputRef} type="file" style={{ display: 'none' }} onChange={handleGroupFileSelected} />
            )}
            <button
              className="w-5 h-5 flex items-center justify-center rounded text-muted-foreground/60 hover:bg-muted hover:text-foreground transition-colors opacity-0 group-hover:opacity-100"
              onClick={(e) => { e.stopPropagation(); setGroupMenuOpen((v) => !v); }}
              title="More options"
            >
              <MoreHorizontal size={12} />
            </button>
            {groupMenuOpen && (
              <div className="absolute right-0 top-full z-20 mt-0.5 w-32 bg-popover border border-border rounded-md shadow-lg py-1">
                {onUpload && (
                  <button
                    className="w-full text-left px-3 py-1.5 text-xs text-foreground hover:bg-accent"
                    onClick={handleGroupUploadClick}
                  >
                    Upload file
                  </button>
                )}
                {onCreateFolder && (
                  <button
                    className="w-full text-left px-3 py-1.5 text-xs text-foreground hover:bg-accent"
                    onClick={handleCreateFolderClick}
                  >
                    New folder
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
      {showFolderInput && (
        <div className="flex items-center gap-1 px-2 py-1.5 border-b border-border bg-muted/40">
          <input
            autoFocus
            type="text"
            className="flex-1 bg-input border border-border rounded-md px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring"
            placeholder="state/crop"
            value={folderName}
            onChange={(e) => setFolderName(e.target.value)}
            onBlur={commitFolder}
            onKeyDown={(e) => { if (e.key === 'Enter') commitFolder(); if (e.key === 'Escape') { setShowFolderInput(false); setFolderName(''); } }}
          />
          <button
            className="flex-shrink-0 px-2 py-1 text-xs bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
            onClick={commitFolder}
          >
            Create
          </button>
        </div>
      )}
      {content}
    </>
  );
}
