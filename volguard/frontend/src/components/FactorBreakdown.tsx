import React from 'react';
import { GateResult } from '../types';

const clampPct = (v: number): number => Math.min(Math.max(v, 0), 100);

interface FactorGaugeProps {
  label: string;
  display: string;
  thresholdLabel: string;
  fillPct: number;
  thresholdPct: number;
  passed: boolean;
}

const FactorGauge: React.FC<FactorGaugeProps> = ({
  label, display, thresholdLabel, fillPct, thresholdPct, passed
}) => {
  const color = passed ? 'var(--green)' : 'var(--amber)';

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: '6px',
      padding: '12px'
    }}>
      {/* Label + pass/fail chip */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '6px'
      }}>
        <span style={{
          fontFamily: 'var(--font-ui)',
          fontSize: '10px',
          fontWeight: 600,
          color: 'var(--muted)',
          letterSpacing: '0.1em'
        }}>
          {label}
        </span>
        <span style={{
          fontFamily: 'var(--font-ui)',
          fontSize: '9px',
          fontWeight: 700,
          letterSpacing: '0.1em',
          padding: '2px 7px',
          borderRadius: '3px',
          color: passed ? '#00e676' : '#ffab00',
          background: passed ? '#00e67615' : '#ffab0015',
          border: `1px solid ${passed ? '#00e67644' : '#ffab0044'}`
        }}>
          {passed ? 'PASS' : 'FAIL'}
        </span>
      </div>

      {/* Current value */}
      <div style={{
        fontFamily: 'var(--font-data)',
        fontSize: '20px',
        fontWeight: 600,
        color,
        marginBottom: '8px'
      }}>
        {display}
      </div>

      {/* Gauge bar with threshold marker */}
      <div style={{
        position: 'relative',
        height: '8px',
        background: 'var(--surface2)',
        border: '1px solid var(--border2)',
        borderRadius: '4px'
      }}>
        <div style={{
          position: 'absolute',
          left: 0,
          top: 0,
          height: '100%',
          width: `${clampPct(fillPct)}%`,
          background: color,
          borderRadius: '4px',
          transition: 'width 0.6s ease'
        }} />
        <div style={{
          position: 'absolute',
          left: `${clampPct(thresholdPct)}%`,
          top: '-3px',
          width: '2px',
          height: '14px',
          background: 'var(--text)',
          opacity: 0.7,
          borderRadius: '1px'
        }} />
      </div>

      {/* Threshold label */}
      <div style={{
        fontFamily: 'var(--font-data)',
        fontSize: '10px',
        color: 'var(--muted)',
        marginTop: '6px',
        textAlign: 'right'
      }}>
        THRESHOLD {thresholdLabel}
      </div>
    </div>
  );
};

interface FactorBreakdownProps {
  dce?: GateResult | null;
}

const FactorBreakdown: React.FC<FactorBreakdownProps> = ({ dce }) => {
  const gss = dce?.gss ?? 0;
  const vanna = dce?.vanna ?? 0;
  const ivSkew = dce?.iv_skew ?? 0;
  const ivRank = dce?.iv_rank ?? 0;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <div style={{
        fontFamily: 'var(--font-ui)',
        fontSize: '10px',
        fontWeight: 600,
        color: 'var(--muted)',
        letterSpacing: '0.1em',
        marginBottom: '4px'
      }}>
        FACTOR BREAKDOWN
      </div>

      <FactorGauge
        label="GSS — GAMMA SQUEEZE SCORE"
        display={gss.toFixed(2)}
        thresholdLabel="≥ 0.60"
        fillPct={gss * 100}
        thresholdPct={60}
        passed={gss >= 0.6}
      />

      <FactorGauge
        label="VANNA"
        display={vanna.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        thresholdLabel="|x| ≥ 5,000"
        fillPct={(Math.abs(vanna) / 10000) * 100}
        thresholdPct={50}
        passed={Math.abs(vanna) >= 5000}
      />

      <FactorGauge
        label="IV SKEW"
        display={ivSkew.toFixed(2)}
        thresholdLabel="|x| > 3.00"
        fillPct={(Math.abs(ivSkew) / 6) * 100}
        thresholdPct={50}
        passed={Math.abs(ivSkew) > 3.0}
      />

      <FactorGauge
        label="IV RANK"
        display={ivRank.toFixed(1)}
        thresholdLabel="0 – 100 · ≥ 50"
        fillPct={ivRank}
        thresholdPct={50}
        passed={ivRank >= 50}
      />
    </div>
  );
};

export default FactorBreakdown;
