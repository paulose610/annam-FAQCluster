import { useState } from 'react';
import { ChevronDown, ChevronRight, Folder } from 'lucide-react';
import FileRow from './FileRow.jsx';

function buildTree(files) {
  const root = { folders: {}, files: [] };
  for (const file of files) {
    const parts = file.path.split('/');
    let node = root;
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i];
      if (!node.folders[part]) node.folders[part] = { folders: {}, files: [] };
      node = node.folders[part];
    }
    node.files.push(file);
  }
  return root;
}

function TreeNode({ name, node, depth, onDeleted }) {
  const [open, setOpen] = useState(true);
  const folderKeys = Object.keys(node.folders).sort();
  const indent = 8 + depth * 14;

  return (
    <>
      {name && (
        <div
          className="flex items-center gap-1 py-1 text-xs text-muted-foreground cursor-pointer hover:bg-accent transition-colors"
          style={{ paddingLeft: `${indent}px`, paddingRight: '8px' }}
          onClick={() => setOpen((v) => !v)}
        >
          <span className="text-muted-foreground/60 flex-shrink-0">
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>
          <Folder size={12} className="flex-shrink-0 text-muted-foreground/60" />
          <span className="truncate">{name}</span>
        </div>
      )}
      {open && (
        <>
          {folderKeys.map((k) => (
            <TreeNode
              key={k}
              name={k}
              node={node.folders[k]}
              depth={name ? depth + 1 : depth}
              onDeleted={onDeleted}
            />
          ))}
          {node.files.map((file) => (
            <FileRow
              key={file.path}
              file={file}
              onDeleted={onDeleted}
              depth={name ? depth + 1 : depth}
            />
          ))}
        </>
      )}
    </>
  );
}

function SubGroup({ label, files, onDeleted }) {
  const [open, setOpen] = useState(true);
  return (
    <>
      <div
        className="flex items-center gap-1 px-3 py-1 text-xs text-muted-foreground cursor-pointer hover:bg-accent transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-muted-foreground/60 flex-shrink-0">
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>
        <Folder size={12} className="flex-shrink-0 text-muted-foreground/60" />
        <span className="truncate">{label}</span>
      </div>
      {open &&
        files.map((file) => (
          <FileRow key={file.path} file={file} onDeleted={onDeleted} />
        ))}
    </>
  );
}

export default function FileGroup({ label, files, onDeleted, groupBy, showPath = false }) {
  const [open, setOpen] = useState(true);

  let content = null;
  if (open) {
    if (showPath) {
      if (files.length === 0) {
        content = <div className="px-4 py-2 text-xs text-muted-foreground/60 italic">No files</div>;
      } else {
        const tree = buildTree(files);
        content = <TreeNode name={null} node={tree} depth={0} onDeleted={onDeleted} />;
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
        content = keys.map((k) => (
          <SubGroup key={k} label={k} files={groups[k]} onDeleted={onDeleted} />
        ));
      }
    } else {
      if (files.length === 0) {
        content = <div className="px-4 py-2 text-xs text-muted-foreground/60 italic">No files</div>;
      } else {
        content = files.map((file) => (
          <FileRow key={file.path} file={file} onDeleted={onDeleted} />
        ));
      }
    }
  }

  return (
    <>
      <div
        className="flex items-center gap-1.5 px-3 py-2 cursor-pointer bg-muted hover:bg-accent transition-colors border-y border-border"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="text-muted-foreground/60 flex-shrink-0">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <span className="text-xs font-semibold text-foreground/70 uppercase tracking-wider">{label}</span>
      </div>
      {content}
    </>
  );
}
