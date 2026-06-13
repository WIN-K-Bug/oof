import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';
import {
  BacktestResult,
  BacktestSummary,
  BacktestDayResult,
  BacktestSignal
} from '../types';

const API_BASE = 'http://localhost:8000';

interface SummaryCardProps {
  summary: BacktestSummary;
}

const SummaryCard: React.FC<SummaryCardProps> = ({ summary }) => {
  const pnlColor = summary.total_pnl >= 0 ? 'var(--green)' : 'var(--red)';
  const winRateColor = summary.win_rate >= 50 ? 'var(--green)' : 'var(--red)';

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: '8px',
      padding: '20px 24px',
      marginBottom: '16px'
    }}>
      <div style={{
        fontSize: '10px',
        color: 'var(--muted)',
        letterSpacing: '0.1em',
        marginBottom: '16px',
        fontFamily: 'var(--font-ui)'
      }}>
        WEEKLY BACKTEST SUMMARY — {summary.date_from} to {summary.date_to}
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(6, 1fr)',
        gap: '24px'
      }}>
        {[
          { label: 'TOTAL SIGNALS', value: summary.total_signals, color: 'var(--text)' },
          { label: 'WIN RATE', value: `${summary.win_rate}%`, color: winRateColor },
          { label: 'WINS', value: summary.wins, color: 'var(--green)' },
          { label: 'LOSSES', value: summary.losses, color: 'var(--red)' },
          { label: 'EXPIRED', value: summary.expired, color: 'var(--amber)' },
          { label: 'TOTAL P&L', value: `₹${summary.total_pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`, color: pnlColor }
        ].map(({ label, value, color }) => (
          <div key={label}>
            <div style={{
              fontSize: '10px',
              color: 'var(--muted)',
              letterSpacing: '0.08em',
              marginBottom: '6px',
              fontFamily: 'var(--font-ui)'
            }}>
              {label}
            </div>
            <div style={{
              fontFamily: 'var(--font-data)',
              fontSize: '22px',
              fontWeight: 600,
              color
            }}>
              {value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

interface TradeRowProps {
  signal: BacktestSignal;
  index: number;
}

const TradeRow: React.FC<TradeRowProps> = ({ signal, index }) => {
  const isWin = signal.outcome === 'WIN';
  const isLoss = signal.outcome === 'LOSS';
  const isCE = signal.signal_type.includes('CE');

  const rowBg = isWin ? '#00e67611' : isLoss ? '#ff3d5711' : '#ffab0011';
  const outcomeColor = isWin ? 'var(--green)' : isLoss ? 'var(--red)' : 'var(--amber)';
  const signalColor = isCE ? 'var(--green)' : 'var(--red)';
  const pnlColor = signal.pnl > 0 ? 'var(--green)' : signal.pnl < 0 ? 'var(--red)' : 'var(--muted)';

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '60px 90px 80px 100px 80px 80px 80px 70px 80px 80px',
      gap: '8px',
      padding: '10px 16px',
      background: index % 2 === 0 ? rowBg : 'transparent',
      borderBottom: '1px solid var(--border)',
      alignItems: 'center',
      fontSize: '12px'
    }}>
      <span style={{ fontFamily: 'var(--font-data)', color: 'var(--muted)' }}>
        {signal.time}
      </span>
      <span style={{ fontFamily: 'var(--font-ui)', color: signalColor, fontWeight: 600 }}>
        {isCE ? '▲ BUY CE' : '▼ BUY PE'}
      </span>
      <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text)' }}>
        {signal.strike.toLocaleString('en-IN')}
      </span>
      <span style={{ fontFamily: 'var(--font-data)', color: 'var(--muted)', fontSize: '11px' }}>
        {signal.symbol}
      </span>
      <span style={{ fontFamily: 'var(--font-data)', color: 'var(--text)' }}>
        ₹{signal.entry_price.toFixed(2)}
      </span>
      <span style={{ fontFamily: 'var(--font-data)', color: 'var(--red)' }}>
        ₹{signal.stop_loss.toFixed(2)}
      </span>
      <span style={{ fontFamily: 'var(--font-data)', color: 'var(--green)' }}>
        ₹{signal.target.toFixed(2)}
      </span>
      <span style={{ fontFamily: 'var(--font-data)', color: 'var(--muted)' }}>
        {signal.confidence}%
      </span>
      <span style={{
        fontFamily: 'var(--font-ui)',
        color: outcomeColor,
        fontWeight: 600,
        fontSize: '11px',
        padding: '2px 8px',
        background: `${outcomeColor}22`,
        borderRadius: '4px',
        textAlign: 'center'
      }}>
        {signal.outcome}
      </span>
      <span style={{ fontFamily: 'var(--font-data)', color: pnlColor, fontWeight: 600 }}>
        {signal.pnl >= 0 ? '+' : ''}₹{signal.pnl.toFixed(2)}
      </span>
    </div>
  );
};

interface DayAccordionProps {
  date: string;
  dayResult: BacktestDayResult;
  defaultOpen?: boolean;
}

const DayAccordion: React.FC<DayAccordionProps> = ({ date, dayResult, defaultOpen = false }) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const pnlColor = dayResult.day_pnl >= 0 ? 'var(--green)' : 'var(--red)';
  const dayOfWeek = new Date(date).toLocaleDateString('en-IN', { weekday: 'long' });

  return (
    <div style={{
      border: '1px solid var(--border)',
      borderRadius: '8px',
      marginBottom: '8px',
      overflow: 'hidden'
    }}>
      <div
        onClick={() => setIsOpen(!isOpen)}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 20px',
          background: 'var(--surface)',
          cursor: 'pointer',
          userSelect: 'none'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ fontFamily: 'var(--font-data)', fontSize: '13px', fontWeight: 600, color: 'var(--text)' }}>
            {dayOfWeek}
          </span>
          <span style={{ fontFamily: 'var(--font-data)', fontSize: '12px', color: 'var(--muted)' }}>
            {date}
          </span>
          <div style={{ display: 'flex', gap: '12px' }}>
            <span style={{ fontSize: '11px', color: 'var(--green)', fontFamily: 'var(--font-ui)' }}>{dayResult.wins}W</span>
            <span style={{ fontSize: '11px', color: 'var(--red)', fontFamily: 'var(--font-ui)' }}>{dayResult.losses}L</span>
            <span style={{ fontSize: '11px', color: 'var(--amber)', fontFamily: 'var(--font-ui)' }}>{dayResult.expired}E</span>
            <span style={{ fontSize: '11px', color: 'var(--muted)', fontFamily: 'var(--font-ui)' }}>{dayResult.total_signals} signals</span>
            <span style={{ fontSize: '11px', color: 'var(--muted)', fontFamily: 'var(--font-ui)' }}>WR: {dayResult.win_rate}%</span>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
          <span style={{ fontFamily: 'var(--font-data)', fontSize: '15px', fontWeight: 600, color: pnlColor }}>
            {dayResult.day_pnl >= 0 ? '+' : ''}₹{dayResult.day_pnl.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </span>
          <span style={{
            color: 'var(--muted)',
            fontSize: '14px',
            transition: 'transform 0.2s',
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
            display: 'inline-block'
          }}>▼</span>
        </div>
      </div>

      {isOpen && (
        <div style={{ background: 'var(--bg)' }}>
          {dayResult.signals.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--muted)', fontFamily: 'var(--font-ui)', fontSize: '13px' }}>
              No signals fired on this day
            </div>
          ) : (
            <>
              <div style={{
                display: 'grid',
                gridTemplateColumns: '60px 90px 80px 100px 80px 80px 80px 70px 80px 80px',
                gap: '8px',
                padding: '8px 16px',
                borderBottom: '1px solid var(--border2)',
                background: 'var(--surface2)'
              }}>
                {['TIME', 'SIGNAL', 'STRIKE', 'SYMBOL', 'ENTRY', 'SL', 'TARGET', 'CONF', 'OUTCOME', 'P&L'].map(h => (
                  <span key={h} style={{ fontSize: '10px', color: 'var(--muted)', letterSpacing: '0.08em', fontFamily: 'var(--font-ui)' }}>
                    {h}
                  </span>
                ))}
              </div>
              {dayResult.signals.map((signal, i) => (
                <TradeRow key={signal.id ?? i} signal={signal} index={i} />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
};

interface UploadZoneProps {
  onUpload: (file: File) => void;
  isRunning: boolean;
}

const UploadZone: React.FC<UploadZoneProps> = ({ onUpload, isRunning }) => {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && file.name.endsWith('.csv')) onUpload(file);
  };

  return (
    <div
      onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={() => !isRunning && inputRef.current?.click()}
      style={{
        border: `2px dashed ${isDragging ? 'var(--purple)' : 'var(--border2)'}`,
        borderRadius: '8px',
        padding: '32px',
        textAlign: 'center',
        cursor: isRunning ? 'not-allowed' : 'pointer',
        background: isDragging ? '#7c3aed11' : 'var(--surface)',
        transition: 'all 0.2s'
      }}
    >
      <div style={{ fontSize: '24px', marginBottom: '8px' }}>📂</div>
      <div style={{ fontFamily: 'var(--font-ui)', fontSize: '13px', color: 'var(--text)', marginBottom: '4px' }}>
        Drop your CSV file here or click to browse
      </div>
      <div style={{ fontFamily: 'var(--font-ui)', fontSize: '11px', color: 'var(--muted)' }}>
        Required columns: date, time, token, symbol, ltp, oi, volume, iv, bid, ask, spot_price
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        style={{ display: 'none' }}
        onChange={e => {
          const file = e.target.files?.[0];
          if (file) onUpload(file);
        }}
      />
    </div>
  );
};

const BacktestPage: React.FC = () => {
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressMsg, setProgressMsg] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'upload' | 'api'>('upload');
  const [days, setDays] = useState(5);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const pollResults = useCallback(async () => {
    try {
      const res = await axios.get<BacktestResult>(`${API_BASE}/api/backtest/results`);
      const data = res.data;
      setProgress(data.progress ?? 0);
      setProgressMsg(data.progress_message ?? '');
      setResult(data);
      if (data.summary?.error) {
        setError(data.summary.error);
      }
      if (data.status !== 'running') {
        setIsRunning(false);
        if (pollRef.current) clearInterval(pollRef.current);
      }
    } catch {
      setError('Failed to fetch backtest results');
    }
  }, []);

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(pollResults, 1500);
  }, [pollResults]);

  useEffect(() => {
    pollResults();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [pollResults]);

  const handleRunAPI = async () => {
    try {
      setError(null);
      setIsRunning(true);
      setProgress(0);
      await axios.post(`${API_BASE}/api/backtest/run?days=${days}`);
      startPolling();
    } catch {
      setError('Failed to start backtest');
      setIsRunning(false);
    }
  };

  const handleUpload = async (file: File) => {
    try {
      setError(null);
      setIsRunning(true);
      setProgress(0);
      const formData = new FormData();
      formData.append('file', file);
      await axios.post(`${API_BASE}/api/backtest/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      startPolling();
    } catch (err: any) {
      setError(err?.response?.data?.error ?? 'Upload failed');
      setIsRunning(false);
    }
  };

  const summary = result?.summary;
  const dailyResults = result?.daily_results ?? {};
  const sortedDates = Object.keys(dailyResults).sort();

  return (
    <div style={{ height: '100%', overflow: 'auto', padding: '20px 24px', background: 'var(--bg)' }}>

      {/* Page Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-data)', fontSize: '16px', fontWeight: 600, color: 'var(--purple)', letterSpacing: '0.08em', marginBottom: '4px' }}>
            ◈ BACKTEST ENGINE
          </div>
          <div style={{ fontFamily: 'var(--font-ui)', fontSize: '12px', color: 'var(--muted)' }}>
            Replay historical NIFTY data through the 18-gate DCE
          </div>
        </div>
        {result && (
          <div style={{
            padding: '6px 14px',
            borderRadius: '4px',
            background: result.status === 'completed' ? '#00e67622' : result.status === 'running' ? '#ffab0022' : 'var(--surface)',
            border: `1px solid ${result.status === 'completed' ? 'var(--green)' : result.status === 'running' ? 'var(--amber)' : 'var(--border)'}`,
            color: result.status === 'completed' ? 'var(--green)' : result.status === 'running' ? 'var(--amber)' : 'var(--muted)',
            fontFamily: 'var(--font-ui)',
            fontSize: '11px',
            fontWeight: 600,
            letterSpacing: '0.05em'
          }}>
            {result.status.toUpperCase()}
          </div>
        )}
      </div>

      {/* Control Panel */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '8px', padding: '20px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
          {(['upload', 'api'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: '6px 16px',
                borderRadius: '4px',
                border: `1px solid ${activeTab === tab ? 'var(--purple)' : 'var(--border)'}`,
                background: activeTab === tab ? '#7c3aed22' : 'transparent',
                color: activeTab === tab ? 'var(--purple)' : 'var(--muted)',
                fontFamily: 'var(--font-ui)',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                letterSpacing: '0.05em'
              }}
            >
              {tab === 'upload' ? '📂 UPLOAD CSV' : '☁ FETCH FROM API'}
            </button>
          ))}
        </div>

        {activeTab === 'upload' ? (
          <UploadZone onUpload={handleUpload} isRunning={isRunning} />
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div>
              <div style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '6px', fontFamily: 'var(--font-ui)' }}>
                TRADING DAYS TO FETCH
              </div>
              <select
                value={days}
                onChange={e => setDays(Number(e.target.value))}
                disabled={isRunning}
                style={{
                  background: 'var(--surface2)',
                  border: '1px solid var(--border2)',
                  borderRadius: '4px',
                  color: 'var(--text)',
                  padding: '8px 12px',
                  fontFamily: 'var(--font-data)',
                  fontSize: '13px',
                  cursor: 'pointer'
                }}
              >
                {[3, 5, 10].map(d => (
                  <option key={d} value={d}>{d} days</option>
                ))}
              </select>
            </div>
            <div style={{ marginTop: '20px' }}>
              <button
                onClick={handleRunAPI}
                disabled={isRunning}
                style={{
                  padding: '8px 24px',
                  borderRadius: '4px',
                  border: '1px solid var(--purple)',
                  background: isRunning ? 'var(--surface2)' : '#7c3aed33',
                  color: isRunning ? 'var(--muted)' : 'var(--purple)',
                  fontFamily: 'var(--font-ui)',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: isRunning ? 'not-allowed' : 'pointer',
                  letterSpacing: '0.05em'
                }}
              >
                {isRunning ? 'RUNNING...' : 'RUN BACKTEST'}
              </button>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted)', fontFamily: 'var(--font-ui)', marginTop: '20px' }}>
              Requires valid Angel One credentials in .env
            </div>
          </div>
        )}

        {isRunning && (
          <div style={{ marginTop: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ fontFamily: 'var(--font-ui)', fontSize: '11px', color: 'var(--muted)' }}>
                {progressMsg || 'Processing...'}
              </span>
              <span style={{ fontFamily: 'var(--font-data)', fontSize: '11px', color: 'var(--amber)' }}>
                {progress}%
              </span>
            </div>
            <div style={{ height: '4px', background: 'var(--border)', borderRadius: '2px', overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: `${progress}%`,
                background: 'var(--amber)',
                borderRadius: '2px',
                transition: 'width 0.5s ease'
              }} />
            </div>
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div style={{
          padding: '12px 16px',
          background: '#ff3d5722',
          border: '1px solid #ff3d5744',
          borderRadius: '6px',
          color: 'var(--red)',
          fontFamily: 'var(--font-ui)',
          fontSize: '12px',
          marginBottom: '16px'
        }}>
          ⚠ {error}
        </div>
      )}

      {/* Summary card */}
      {result?.status === 'completed' && summary && summary.total_signals > 0 && (
        <SummaryCard summary={summary} />
      )}

      {/* No signals message */}
      {result?.status === 'completed' && summary && summary.total_signals === 0 && (
        <div style={{
          padding: '32px',
          textAlign: 'center',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: '8px',
          marginBottom: '16px',
          color: 'var(--muted)',
          fontFamily: 'var(--font-ui)',
          fontSize: '13px'
        }}>
          No signals fired during the backtest period. Try a different date range or lower the confidence threshold.
        </div>
      )}

      {/* Daily P&L bar strip — shows the shape of the week at a glance */}
      {result?.status === 'completed' && sortedDates.length > 1 && (
        <div style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: '8px',
          padding: '16px 20px',
          marginBottom: '16px'
        }}>
          <div style={{ fontSize: '10px', color: 'var(--muted)', letterSpacing: '0.1em', marginBottom: '12px', fontFamily: 'var(--font-ui)' }}>
            DAILY P&L
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '12px', height: '88px' }}>
            {sortedDates.map(date => {
              const pnl = dailyResults[date]?.day_pnl ?? 0;
              const maxAbs = Math.max(
                ...sortedDates.map(d => Math.abs(dailyResults[d]?.day_pnl ?? 0)),
                1
              );
              const h = Math.max(Math.round((Math.abs(pnl) / maxAbs) * 60), 2);
              return (
                <div key={date} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', gap: '4px' }}>
                  <span style={{ fontFamily: 'var(--font-data)', fontSize: '10px', color: pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                    {pnl >= 0 ? '+' : ''}{Math.round(pnl).toLocaleString('en-IN')}
                  </span>
                  <div style={{
                    width: '100%',
                    maxWidth: '48px',
                    height: `${h}px`,
                    background: pnl >= 0 ? 'var(--green)' : 'var(--red)',
                    opacity: 0.8,
                    borderRadius: '3px'
                  }} />
                  <span style={{ fontFamily: 'var(--font-data)', fontSize: '9px', color: 'var(--muted)' }}>
                    {date.slice(5)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Day-by-day accordion */}
      {result?.status === 'completed' && sortedDates.length > 0 && (
        <div>
          <div style={{ fontSize: '10px', color: 'var(--muted)', letterSpacing: '0.1em', marginBottom: '12px', fontFamily: 'var(--font-ui)' }}>
            DAY-BY-DAY BREAKDOWN
          </div>
          {sortedDates.map((date, i) => (
            <DayAccordion
              key={date}
              date={date}
              dayResult={dailyResults[date]}
              defaultOpen={i === 0}
            />
          ))}
        </div>
      )}

      {/* Idle state */}
      {(!result || result.status === 'idle') && !isRunning && (
        <div style={{ padding: '48px', textAlign: 'center', color: 'var(--muted)', fontFamily: 'var(--font-ui)', fontSize: '13px' }}>
          Upload a CSV file or fetch from Angel One API to run a backtest
        </div>
      )}
    </div>
  );
};

export default BacktestPage;
