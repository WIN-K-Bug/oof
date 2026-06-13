import React, { useState } from 'react';
import './index.css';
import Dashboard from './components/Dashboard';
import BacktestPage from './components/BacktestPage';

type Tab = 'live' | 'backtest';

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('live');

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      background: 'var(--bg)',
      overflow: 'hidden'
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '4px',
        padding: '0 24px',
        height: '40px',
        background: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0
      }}>
        {([
          { id: 'live', label: '◉ LIVE DASHBOARD' },
          { id: 'backtest', label: '◈ BACKTEST' }
        ] as { id: Tab; label: string }[]).map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '0 16px',
              height: '40px',
              border: 'none',
              borderBottom: `2px solid ${activeTab === tab.id ? 'var(--purple)' : 'transparent'}`,
              background: 'transparent',
              color: activeTab === tab.id ? 'var(--text)' : 'var(--muted)',
              fontFamily: 'var(--font-ui)',
              fontSize: '11px',
              fontWeight: activeTab === tab.id ? 600 : 400,
              letterSpacing: '0.08em',
              cursor: 'pointer',
              transition: 'color 0.15s'
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {activeTab === 'live' ? <Dashboard /> : <BacktestPage />}
      </div>
    </div>
  );
};

export default App;
