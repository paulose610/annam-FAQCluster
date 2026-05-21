import { useState } from 'react';
import { Toaster } from 'sonner';
import Header from './components/Header.jsx';
import FunctionsPanel from './components/FunctionsPanel/FunctionsPanel.jsx';
import PopTranslationPanel from './components/FunctionsPanel/PopTranslationPanel.jsx';

const TABS = [
  { id: 'faq-cluster', label: 'FAQ-Cluster' },
  { id: 'pop-translation', label: 'POP-Translation' },
  { id: 'outreach', label: 'Outreach' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('faq-cluster');

  return (
    <div className="flex flex-col h-screen">
      <Header />
      <div className="flex-1 overflow-y-auto bg-background flex flex-col">
        <div className="flex justify-center gap-1 border-b border-border px-4 py-2.5 flex-shrink-0">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors
                ${activeTab === tab.id
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {activeTab === 'faq-cluster' && <FunctionsPanel />}
          {activeTab === 'pop-translation' && <PopTranslationPanel onJobCreated={() => {}} />}
          {activeTab === 'outreach' && (
            <div className="flex items-center justify-center h-40">
              <p className="text-muted-foreground text-sm italic">Coming soon</p>
            </div>
          )}
        </div>
      </div>
      <Toaster richColors position="bottom-right" />
    </div>
  );
}
