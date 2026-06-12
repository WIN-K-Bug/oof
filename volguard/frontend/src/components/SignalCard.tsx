import React from 'react';
import { Signal } from '../types';

interface SignalCardProps {
  signal?: Signal | null;
}

const formatTimestamp = (ts?: string): string => {
  if (!ts) return '—';
  const d = new Date(ts);
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' });
};

interface PriceCellProps {
  label: string;
  value?: number;
  color: string;
}

const PriceCell: React.FC<PriceCellProps> = ({ label, value, color }) => (
  <div style={{
    background: 'var(--surface2)',
    border: '1px solid var(--border2)',
    borderRadius: '6px',
    padding: '12px',
    textAlign: 'center'
  }}>
    <div style={{
      fontFamily: 'var(--font-ui)',
      fontSize: '10px',
      color: 'var(--muted)',
      letterSpacing: '0.1em',
      marginBottom: '4px'
    }}>
      {label}
    </div>
    <div style={{
      fontFamily: 'var(--font-data)',
      fontSize: '18px',
      fontWeight: 600,
      color
    }}>
      ₹{(value ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
    </div>
  </div>
);

const SignalCard: React.FC<SignalCardProps> = ({ signal }) => {
  const type = signal?.signal ?? 'NO_TRADE';
  const isCE = type === 'BUY_CE';
  const isPE = type === 'BUY_PE';
  const isActive = isCE || isPE;

  if (!isActive) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        flex: 1,
        minHeight: '300px',
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: '8px',
        padding: '32px',
        gap: '12px'
      }}>
        <div style={{
          fontFamily: 'var(--font-data)',
          fontSize: '28px',
          color: 'var(--muted2)'
        }}>
          ◌
        </div>
        <div style={{
          fontFamily: 'var(--font-ui)',
          fontSize: '14px',
          fontWeight: 600,
          color: 'var(--muted)',
          letterSpacing: '0.12em'
        }}>
          NO ACTIVE SIGNAL
        </div>
        <div style={{
          fontFamily: 'var(--font-ui)',
          fontSize: '12px',
          color: 'var(--muted)',
          textAlign: 'center',
          maxWidth: '360px',
          lineHeight: 1.6
        }}>
          {signal?.reason ?? 'Scanning market — waiting for all 18 gates to align.'}
        </div>
        {signal?.cooldown_active && (
          <div style={{
            fontFamily: 'var(--font-ui)',
            fontSize: '11px',
            color: 'var(--amber)',
            padding: '4px 12px',
            background: '#ffab0018',
            border: '1px solid #ffab0044',
            borderRadius: '4px',
            letterSpacing: '0.05em'
          }}>
            ⏳ COOLDOWN ACTIVE
          </div>
        )}
      </div>
    );
  }

  const color = isCE ? 'var(--green)' : 'var(--red)';
  const headerLabel = isCE ? '▲ BUY CALL' : '▼ BUY PUT';
  const confidence = signal?.confidence_score ?? 0;

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--surface)',
      border: `1px solid ${isCE ? '#00e67644' : '#ff3d5744'}`,
      borderRadius: '8px',
      overflow: 'hidden'
    }}>
      {/* Large colored header */}
      <div style={{
        padding: '16px 20px',
        background: isCE ? '#00e67615' : '#ff3d5715',
        borderBottom: `1px solid ${isCE ? '#00e67633' : '#ff3d5733'}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <span style={{
          fontFamily: 'var(--font-ui)',
          fontSize: '22px',
          fontWeight: 700,
          color,
          letterSpacing: '0.08em'
        }}>
          {headerLabel}
        </span>
        {signal?.cooldown_active ? (
          <span style={{
            fontFamily: 'var(--font-ui)',
            fontSize: '11px',
            color: 'var(--amber)',
            padding: '4px 10px',
            background: '#ffab0018',
            border: '1px solid #ffab0044',
            borderRadius: '4px',
            letterSpacing: '0.05em'
          }}>
            ⏳ COOLDOWN
          </span>
        ) : (
          <span style={{
            fontFamily: 'var(--font-ui)',
            fontSize: '11px',
            color,
            padding: '4px 10px',
            background: 'var(--surface2)',
            border: `1px solid ${isCE ? '#00e67644' : '#ff3d5744'}`,
            borderRadius: '4px',
            letterSpacing: '0.05em'
          }}>
            ● LIVE
          </span>
        )}
      </div>

      <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {/* Symbol + expiry */}
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
          <span style={{
            fontFamily: 'var(--font-data)',
            fontSize: '14px',
            fontWeight: 600,
            color: 'var(--text)'
          }}>
            {signal?.symbol ?? '—'}
          </span>
          <span style={{
            fontFamily: 'var(--font-ui)',
            fontSize: '11px',
            color: 'var(--muted)',
            letterSpacing: '0.05em'
          }}>
            EXPIRY: {signal?.expiry ?? '—'}
          </span>
        </div>

        {/* Strike price */}
        <div style={{ textAlign: 'center', padding: '8px 0' }}>
          <div style={{
            fontFamily: 'var(--font-ui)',
            fontSize: '10px',
            color: 'var(--muted)',
            letterSpacing: '0.12em',
            marginBottom: '4px'
          }}>
            STRIKE
          </div>
          <div style={{
            fontFamily: 'var(--font-data)',
            fontSize: '40px',
            fontWeight: 600,
            color: 'var(--text)',
            lineHeight: 1.1
          }}>
            {(signal?.strike_price ?? 0).toLocaleString('en-IN')}
          </div>
        </div>

        {/* Entry / SL / Target grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
          <PriceCell label="ENTRY" value={signal?.entry_price} color="var(--text)" />
          <PriceCell label="STOP LOSS" value={signal?.stop_loss} color="var(--red)" />
          <PriceCell label="TARGET" value={signal?.target} color="var(--green)" />
        </div>

        {/* Risk:Reward */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 14px',
          background: 'var(--surface2)',
          border: '1px solid var(--border2)',
          borderRadius: '6px'
        }}>
          <span style={{
            fontFamily: 'var(--font-ui)',
            fontSize: '11px',
            color: 'var(--muted)',
            letterSpacing: '0.1em'
          }}>
            RISK : REWARD
          </span>
          <span style={{
            fontFamily: 'var(--font-data)',
            fontSize: '16px',
            fontWeight: 600,
            color: 'var(--purple)'
          }}>
            1 : {(signal?.risk_reward ?? 0).toFixed(2)}
          </span>
        </div>

        {/* Confidence bar */}
        <div>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginBottom: '6px'
          }}>
            <span style={{
              fontFamily: 'var(--font-ui)',
              fontSize: '10px',
              color: 'var(--muted)',
              letterSpacing: '0.1em'
            }}>
              CONFIDENCE
            </span>
            <span style={{
              fontFamily: 'var(--font-data)',
              fontSize: '13px',
              fontWeight: 600,
              color
            }}>
              {confidence}%
            </span>
          </div>
          <div style={{
            height: '8px',
            background: 'var(--border)',
            borderRadius: '4px',
            overflow: 'hidden'
          }}>
            <div style={{
              height: '100%',
              width: `${Math.min(Math.max(confidence, 0), 100)}%`,
              background: color,
              borderRadius: '4px',
              transition: 'width 0.8s ease',
              boxShadow: `0 0 8px ${isCE ? '#00e67666' : '#ff3d5766'}`
            }} />
          </div>
        </div>

        {/* Timestamp */}
        <div style={{
          fontFamily: 'var(--font-data)',
          fontSize: '11px',
          color: 'var(--muted)',
          textAlign: 'right'
        }}>
          SIGNAL TIME: {formatTimestamp(signal?.timestamp)}
        </div>
      </div>
    </div>
  );
};

export default SignalCard;
