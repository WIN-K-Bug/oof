import React from 'react';
import { GateResult } from '../types';

const GATE_NAMES: string[] = [
  'Daily Loss Limit',
  'Market Hours',
  'Tick Health',
  'Spot Price Valid',
  'VWAP Calculated',
  'Spot vs VWAP',
  'Signal Cooldown',
  'VolGuard Active',
  'Min Tick Count',
  'Options Data',
  'Price Momentum',
  'GSS Threshold',
  'Vanna Threshold',
  'IV Skew + Rank',
  'Bid-Ask Spread',
  'Volume Floor',
  'OI Concentration',
  'Directional Alignment'
];

const extractIndex = (key: string): number => {
  const match = key.match(/\d+/);
  return match ? parseInt(match[0], 10) : 999;
};

interface GateRow {
  key: string;
  index: number;
  name: string;
  passed: boolean;
  detail: string;
}

interface GateStatusProps {
  dce?: GateResult | null;
}

const GateStatus: React.FC<GateStatusProps> = ({ dce }) => {
  const results = dce?.gate_results ?? {};
  const details = dce?.gate_details ?? {};
  const totalGates = dce?.total_gates ?? 18;

  const keys = Object.keys(results);

  const rows: GateRow[] = keys.length > 0
    ? keys
        .map((key) => {
          const index = extractIndex(key);
          return {
            key,
            index,
            name: GATE_NAMES[index] ?? key.replace(/_/g, ' ').toUpperCase(),
            passed: !!results[key],
            detail: details[key] ?? ''
          };
        })
        .sort((a, b) => a.index - b.index)
    : GATE_NAMES.map((name, i) => ({
        key: `gate_${i}`,
        index: i,
        name,
        passed: false,
        detail: 'Awaiting data...'
      }));

  const passedCount = dce?.gates_passed ?? rows.filter((r) => r.passed).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Header with passed count */}
      <div style={{
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        marginBottom: '12px',
        flexShrink: 0
      }}>
        <span style={{
          fontFamily: 'var(--font-ui)',
          fontSize: '10px',
          color: 'var(--muted)',
          letterSpacing: '0.1em',
          fontWeight: 600
        }}>
          GATE STATUS
        </span>
        <span style={{
          fontFamily: 'var(--font-data)',
          fontSize: '13px',
          fontWeight: 600,
          color: passedCount === totalGates ? 'var(--green)' : 'var(--text)'
        }}>
          {passedCount} / {totalGates} GATES
        </span>
      </div>

      {/* Scrollable gate list */}
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '4px',
        overflowY: 'auto',
        flex: 1,
        minHeight: 0
      }}>
        {rows.map((row) => (
          <div
            key={row.key}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '8px',
              padding: '7px 10px',
              borderRadius: '4px',
              background: row.passed ? '#e8f5e9' : '#4a2c2c',
              border: `1px solid ${row.passed ? '#00e67633' : '#ff3d5733'}`
            }}
          >
            <div style={{
              width: '7px',
              height: '7px',
              borderRadius: '50%',
              marginTop: '4px',
              flexShrink: 0,
              background: row.passed ? '#00e676' : '#ff3d57',
              boxShadow: row.passed ? '0 0 4px #00e676' : '0 0 4px #ff3d5788'
            }} />
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{
                fontFamily: 'var(--font-ui)',
                fontSize: '11px',
                fontWeight: 600,
                color: row.passed ? '#12121a' : '#ff8a7a',
                letterSpacing: '0.02em'
              }}>
                {row.index}. {row.name}
              </div>
              {row.detail && (
                <div style={{
                  fontFamily: 'var(--font-data)',
                  fontSize: '10px',
                  color: row.passed ? '#4a6a4a' : '#b0837a',
                  marginTop: '1px',
                  wordBreak: 'break-word'
                }}>
                  {row.detail}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default GateStatus;
