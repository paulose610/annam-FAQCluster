import { useState, useEffect } from 'react';
import { Moon, Sun } from 'lucide-react';

export default function Header() {
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark');

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('theme', dark ? 'dark' : 'light');
  }, [dark]);

  return (
    <header className="h-12 flex-shrink-0 border-b border-border bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60 flex items-center px-4 justify-between z-50">
      <span className="font-semibold text-lg text-foreground tracking-wide">KCC-FAQ-Cluster</span>
      <button
        onClick={() => setDark((d) => !d)}
        className="w-8 h-8 flex items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
        title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
      >
        {dark ? <Sun size={16} /> : <Moon size={16} />}
      </button>
    </header>
  );
}
