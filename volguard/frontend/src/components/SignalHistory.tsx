import React from 'react';
import { SignalHistoryItem } from '../types';

interface OutcomeStyle {
  color: string;
  background: string;
  border: string;
}

const outcomeStyle = (outcome?: string): OutcomeStyle => {
  switch ((outcome ?? 'PENDING').toUpperCase()) {
    case 'WIN':
      return { color: '#00e676', background: '#00e67615', border: '#00e67644' };
    case 'LOSS':
      return { color: '#ff3d57', background: '#ff3d5715', border: '#ff3d5744' };
    case 'EXPIRED':
      return { color: 'var(--muted)', background: 'var(--surface2)', border: 'var(--border2)' };
    case 'PENDING':
    default:
      return { color: '#ffab00', background: '#ffab0015', border: '#ffab0044' };
  }
};

const formatTime = (ts?: string): string => {
  if (!ts) return '—';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false });
};

const signalType = (item: SignalHistoryItem): string => {
  const raw = item.signal_type ?? item.signal ?? item.direction ?? '';
  if (raw.includes('CE')) return 'CE';
  if (raw.includes('PE')) return 'PE';
  return raw || '—';
};

interface SignalHistoryProps {
  history?: SignalHistoryItem[] | null;
}

const SignalHistory: React.FC<SignalHistoryProps> = ({ history }) => {
  const items = (Array.isArray(history) ? history : []).slice(0, 10);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '16px' }}>
      <div style={{
        fontFamily: 'var(--font-ui)',
        fontSize: '10px',
        fontWeight: 600,
        color: 'var(--muted)',
        letterSpacing: '0.1em',
        marginBottom: '4px'
      }}>
        SIGNAL HISTORY
      </div>

      {items.length === 0 && (
        <div style={{
          fontFamily: 'var(--font-ui)',
          fontSize: '11px',
          color: 'var(--muted)',
          padding: '12px',
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: '6px',
          textAlign: 'center'
        }}>
          No signals recorded yet
        </div>
      )}

      {items.map((item, i) => {
        const type = signalType(item);
        const typeColor = type === 'CE' ? 'var(--green)' : type === 'PE' ? 'var(--red)' : 'var(--muted)';
        const outcome = (item.outcome ?? 'PENDING').toUpperCase();
        const oStyle = outcomeStyle(item.outcome);
        const strike = item.strike_price ?? item.strike;
        const confidence = item.confidence_score ?? item.confidence;

        return (
          <div
            key={item.id ?? `${item.timestamp ?? ''}-${i}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '7px 10px',
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: '5px'
            }}
          >
            <span style={{
              fontFamily: 'var(--font-data)',
              fontSize: '10px',
              color: 'var(--muted)',
              minWidth: '56px'
            }}>
              {formatTime(item.timestamp)}
            </span>
            <span style={{
              fontFamily: 'var(--font-data)',
              fontSize: '11px',
              fontWeight: 600,
              color: typeColor,
              minWidth: '24px'
            }}>
              {type}
            </span>
            <span style={{
              fontFamily: 'var(--font-data)',
              fontSize: '11px',
              color: 'var(--text)',
              flex: 1
            }}>
              {strike != null ? strike.toLocaleString('en-IN') : '—'}
            </span>
            <span style={{
              fontFamily: 'var(--font-data)',
              fontSize: '11px',
              color: 'var(--purple)',
              minWidth: '36px',
              textAlign: 'right'
            }}>
              {confidence != null ? `${confidence}%` : '—'}
            </span>
            <span style={{
              fontFamily: 'var(--font-ui)',
              fontSize: '9px',
              fontWeight: 700,
              letterSpacing: '0.08em',
              padding: '2px 6px',
              borderRadius: '3px',
              color: oStyle.color,
              background: oStyle.background,
              border: `1px solid ${oStyle.border}`,
              minWidth: '54px',
              textAlign: 'center'
            }}>
              {outcome}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export default SignalHistory;
