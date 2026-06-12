import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { DashboardData } from '../types';

const API_BASE = 'http://localhost:8000';
const POLL_INTERVAL = 1000;

function useTickPulse(tickCount: number): boolean {
  const [isPulsing, setIsPulsing] = useState(false);
  const prevTickRef = useRef(tickCount);

  useEffect(() => {
    if (tickCount !== prevTickRef.current) {
      prevTickRef.current = tickCount;
      setIsPulsing(true);
      const timer = setTimeout(() => setIsPulsing(false), 150);
      return () => clearTimeout(timer);
    }
  }, [tickCount]);

  return isPulsing;
}

interface ConvictionBarProps {
  confidence: number;
  gatesPassed: number;
  totalGates: number;
  direction: string;
}

const ConvictionBar: React.FC<ConvictionBarProps> = ({
  confidence, gatesPassed, totalGates, direction
}) => {
  const color = confidence >= 75
    ? '#00e676'
    : confidence >= 50
    ? '#ffab00'
    : '#7c3aed';

  const label = confidence >= 75
    ? direction === 'CE' ? '▲ BULLISH SIGNAL' : '▼ BEARISH SIGNAL'
    : confidence >= 50
    ? '◈ BUILDING CONVICTION'
    : '◌ SCANNING MARKET';

  return (
    <div style={{
      width: '100%',
      background: 'var(--surface)',
      borderBottom: '1px solid var(--border)',
      padding: '12px 24px',
      display: 'flex',
      alignItems: 'center',
      gap: '16px'
    }}>
      <span style={{
        fontFamily: 'var(--font-ui)',
        fontSize: '11px',
        fontWeight: 700,
        letterSpacing: '0.12em',
        color,
        minWidth: '180px'
      }}>
        {label}
      </span>

      <div style={{
        flex: 1,
        height: '6px',
        background: 'var(--border)',
        borderRadius: '3px',
        overflow: 'hidden'
      }}>
        <div style={{
          height: '100%',
          width: `${confidence}%`,
          background: color,
          borderRadius: '3px',
          transition: 'width 0.8s ease, background 0.5s ease',
          boxShadow: confidence >= 75 ? `0 0 8px ${color}66` : 'none'
        }} />
      </div>

      <span style={{
        fontFamily: 'var(--font-data)',
        fontSize: '13px',
        fontWeight: 600,
        color,
        minWidth: '80px',
        textAlign: 'right'
      }}>
        {gatesPassed}/{totalGates} gates
      </span>

      <span style={{
        fontFamily: 'var(--font-data)',
        fontSize: '20px',
        fontWeight: 600,
        color,
        minWidth: '60px',
        textAlign: 'right'
      }}>
        {confidence}%
      </span>
    </div>
  );
};

interface StatusBadgeProps {
  label: string;
  active: boolean;
  activeColor?: string;
  inactiveColor?: string;
}

const StatusBadge: React.FC<StatusBadgeProps> = ({
  label, active,
  activeColor = '#00e676',
  inactiveColor = '#ff3d57'
}) => (
  <div style={{
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 10px',
    background: 'var(--surface2)',
    borderRadius: '4px',
    border: `1px solid ${active ? activeColor + '33' : inactiveColor + '33'}`
  }}>
    <div style={{
      width: '6px',
      height: '6px',
      borderRadius: '50%',
      background: active ? activeColor : inactiveColor,
      boxShadow: active ? `0 0 4px ${activeColor}` : 'none'
    }} />
    <span style={{
      fontFamily: 'var(--font-ui)',
      fontSize: '11px',
      fontWeight: 500,
      color: active ? activeColor : 'var(--muted)',
      letterSpacing: '0.05em'
    }}>
      {label}
    </span>
  </div>
);

const Dashboard: React.FC = () => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>('');

  const tickCount = data?.tick_count ?? 0;
  const isPulsing = useTickPulse(tickCount);

  const fetchData = useCallback(async () => {
    try {
      const res = await axios.get<DashboardData>(`${API_BASE}/api/dashboard`);
      setData(res.data);
      setLastUpdated(new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' }));
      setError(null);
    } catch (err) {
      setError('Backend unreachable — check if server is running on port 8000');
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchData]);

  const confidence = data?.dce?.confidence_score ?? 0;
  const gatesPassed = data?.dce?.gates_passed ?? 0;
  const totalGates = data?.dce?.total_gates ?? 18;
  const direction = data?.dce?.direction ?? 'UNKNOWN';

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      background: 'var(--bg)',
      overflow: 'hidden'
    }}>

      {/* Top Header Bar */}
      <header style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
        height: '52px',
        background: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{
            fontFamily: 'var(--font-data)',
            fontSize: '15px',
            fontWeight: 600,
            color: 'var(--purple)',
            letterSpacing: '0.08em'
          }}>
            ◈ VOLGUARD
          </span>
          <span style={{
            fontFamily: 'var(--font-ui)',
            fontSize: '11px',
            color: 'var(--muted)',
            letterSpacing: '0.05em'
          }}>
            NIFTY OPTIONS SIGNAL SYSTEM
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <StatusBadge
            label="WEBSOCKET"
            active={data?.system_status?.websocket_connected ?? false}
          />
          <StatusBadge
            label="MARKET"
            active={data?.system_status?.market_hours_active ?? false}
          />
          <StatusBadge
            label="FEED"
            active={data?.system_status?.tick_healthy ?? false}
          />
          <StatusBadge
            label="VOLGUARD"
            active={!(data?.system_status?.volguard_blocked ?? false)}
            activeColor="#00e676"
            inactiveColor="#ffab00"
          />

          {/* Tick pulse indicator */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 10px',
            background: 'var(--surface2)',
            borderRadius: '4px',
            border: '1px solid var(--border2)'
          }}>
            <div style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: isPulsing ? '#00e676' : 'var(--muted2)',
              boxShadow: isPulsing ? '0 0 6px #00e676' : 'none',
              transition: 'background 0.1s, box-shadow 0.1s'
            }} />
            <span style={{
              fontFamily: 'var(--font-data)',
              fontSize: '11px',
              color: 'var(--muted)'
            }}>
              {tickCount.toLocaleString()} ticks
            </span>
          </div>

          <span style={{
            fontFamily: 'var(--font-data)',
            fontSize: '11px',
            color: 'var(--muted)'
          }}>
            {lastUpdated}
          </span>
        </div>
      </header>

      {/* Conviction Bar */}
      <ConvictionBar
        confidence={confidence}
        gatesPassed={gatesPassed}
        totalGates={totalGates}
        direction={direction}
      />

      {/* Error Banner */}
      {error && (
        <div style={{
          padding: '10px 24px',
          background: '#ff3d5722',
          borderBottom: '1px solid #ff3d5744',
          color: '#ff3d57',
          fontFamily: 'var(--font-ui)',
          fontSize: '12px'
        }}>
          ⚠ {error}
        </div>
      )}

      {/* Spot Price Bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '32px',
        padding: '10px 24px',
        background: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0
      }}>
        <div>
          <div style={{ fontSize: '10px', color: 'var(--muted)', letterSpacing: '0.1em', marginBottom: '2px' }}>
            NIFTY SPOT
          </div>
          <div style={{ fontFamily: 'var(--font-data)', fontSize: '22px', fontWeight: 600, color: 'var(--text)' }}>
            ₹{(data?.market_state?.spot_price ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>

        <div style={{ width: '1px', height: '32px', background: 'var(--border)' }} />

        <div>
          <div style={{ fontSize: '10px', color: 'var(--muted)', letterSpacing: '0.1em', marginBottom: '2px' }}>
            VWAP
          </div>
          <div style={{ fontFamily: 'var(--font-data)', fontSize: '22px', fontWeight: 600, color: 'var(--muted)' }}>
            ₹{(data?.market_state?.vwap ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </div>
        </div>

        <div style={{ width: '1px', height: '32px', background: 'var(--border)' }} />

        <div>
          <div style={{ fontSize: '10px', color: 'var(--muted)', letterSpacing: '0.1em', marginBottom: '2px' }}>
            DIRECTION
          </div>
          <div style={{
            fontFamily: 'var(--font-data)',
            fontSize: '18px',
            fontWeight: 600,
            color: direction === 'CE' ? 'var(--green)' : direction === 'PE' ? 'var(--red)' : 'var(--muted)'
          }}>
            {direction === 'CE' ? '▲ BULLISH' : direction === 'PE' ? '▼ BEARISH' : '— NEUTRAL'}
          </div>
        </div>

        <div style={{ width: '1px', height: '32px', background: 'var(--border)' }} />

        <div>
          <div style={{ fontSize: '10px', color: 'var(--muted)', letterSpacing: '0.1em', marginBottom: '2px' }}>
            MOMENTUM
          </div>
          <div style={{
            fontFamily: 'var(--font-data)',
            fontSize: '18px',
            fontWeight: 600,
            color: (data?.dce?.momentum ?? 0) > 0 ? 'var(--green)' : 'var(--red)'
          }}>
            {(data?.dce?.momentum ?? 0) > 0 ? '+' : ''}{(data?.dce?.momentum ?? 0).toFixed(3)}%
          </div>
        </div>

        <div style={{ width: '1px', height: '32px', background: 'var(--border)' }} />

        <div>
          <div style={{ fontSize: '10px', color: 'var(--muted)', letterSpacing: '0.1em', marginBottom: '2px' }}>
            IV RANK
          </div>
          <div style={{
            fontFamily: 'var(--font-data)',
            fontSize: '18px',
            fontWeight: 600,
            color: (data?.dce?.iv_rank ?? 50) > 70 ? 'var(--red)' : (data?.dce?.iv_rank ?? 50) < 30 ? 'var(--green)' : 'var(--amber)'
          }}>
            {(data?.dce?.iv_rank ?? 50).toFixed(1)}
          </div>
        </div>
      </div>

      {/* Three Column Main Layout */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '280px 1fr 300px',
        flex: 1,
        overflow: 'hidden',
        gap: '0'
      }}>

        {/* LEFT COLUMN — placeholder, filled in Prompt 8 */}
        <div style={{
          borderRight: '1px solid var(--border)',
          overflow: 'auto',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px'
        }}>
          <div style={{ fontSize: '10px', color: 'var(--muted)', letterSpacing: '0.1em', marginBottom: '8px' }}>
            GATE STATUS
          </div>
          <div style={{ color: 'var(--muted)', fontSize: '12px' }}>
            Loading gates...
          </div>
        </div>

        {/* CENTER COLUMN — placeholder, filled in Prompt 8 */}
        <div style={{
          overflow: 'auto',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px'
        }}>
          <div style={{ fontSize: '10px', color: 'var(--muted)', letterSpacing: '0.1em' }}>
            SIGNAL
          </div>
          <div style={{ color: 'var(--muted)', fontSize: '12px' }}>
            Waiting for signal...
          </div>
        </div>

        {/* RIGHT COLUMN — placeholder, filled in Prompt 8 */}
        <div style={{
          borderLeft: '1px solid var(--border)',
          overflow: 'auto',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px'
        }}>
          <div style={{ fontSize: '10px', color: 'var(--muted)', letterSpacing: '0.1em', marginBottom: '8px' }}>
            FACTOR BREAKDOWN
          </div>
          <div style={{ color: 'var(--muted)', fontSize: '12px' }}>
            Loading factors...
          </div>
        </div>

      </div>
    </div>
  );
};

export default Dashboard;
