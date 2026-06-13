export interface GateResult {
  gate_results: Record<string, boolean>;
  gate_details: Record<string, string>;
  gates_passed: number;
  total_gates: number;
  confidence_score: number;
  direction: 'CE' | 'PE' | 'UNKNOWN';
  momentum: number;
  gss: number;
  vanna: number;
  iv_skew: number;
  iv_rank: number;
}

export interface Signal {
  signal: string;
  symbol?: string;
  strike_price?: number;
  expiry?: string;
  entry_price?: number;
  stop_loss?: number;
  target?: number;
  risk_reward?: number;
  spot_price?: number;
  confidence_score?: number;
  gates_passed?: number;
  direction?: string;
  vwap?: number;
  gss?: number;
  vanna?: number;
  iv_skew?: number;
  iv_rank?: number;
  timestamp?: string;
  cooldown_active?: boolean;
  reason?: string;
}

export interface SystemStatus {
  volguard_blocked: boolean;
  market_hours_active: boolean;
  websocket_connected: boolean;
  tick_healthy: boolean;
  daily_loss_limit_hit: boolean;
  uptime_ticks: number;
}

export interface MarketState {
  spot_price: number;
  vwap: number;
  volguard_blocked: boolean;
  market_hours_active: boolean;
  websocket_connected: boolean;
  tick_count: number;
  tick_healthy: boolean;
}

export interface SignalHistoryItem {
  id?: number;
  timestamp?: string;
  signal_type?: string;
  signal?: string;
  direction?: string;
  symbol?: string;
  strike_price?: number;
  strike?: number;
  confidence_score?: number;
  confidence?: number;
  outcome?: string;
}

export interface DashboardData {
  tick_count: number;
  volguard_blocked: boolean;
  market_hours_active: boolean;
  websocket_connected: boolean;
  tick_healthy: boolean;
  daily_loss_limit_hit: boolean;
  spot_price: number;
  vwap: number;
  today_pnl?: number;
  confidence_score: number;
  gates_passed: number;
  system_status: SystemStatus;
  market_state: MarketState;
  dce: GateResult;
  signal: Signal;
}

export interface BacktestSignal {
  id: number;
  run_id: string;
  date: string;
  time: string;
  signal_type: string;
  strike: number;
  symbol: string;
  entry_price: number;
  stop_loss: number;
  target: number;
  outcome: 'WIN' | 'LOSS' | 'EXPIRED';
  pnl: number;
  confidence: number;
  spot_price: number;
  vwap: number;
  momentum: number;
}

export interface BacktestDayResult {
  date: string;
  signals: BacktestSignal[];
  total_signals: number;
  wins: number;
  losses: number;
  expired: number;
  day_pnl: number;
  win_rate: number;
}

export interface BacktestSummary {
  run_id: string;
  date_from: string;
  date_to: string;
  total_signals: number;
  wins: number;
  losses: number;
  expired: number;
  total_pnl: number;
  win_rate: number;
  daily_results: Record<string, BacktestDayResult>;
  error?: string;
}

export interface BacktestResult {
  status: 'idle' | 'running' | 'completed';
  progress: number;
  progress_message: string;
  run_id: string;
  summary: BacktestSummary;
  daily_results: Record<string, BacktestDayResult>;
  runs: BacktestRun[];
}

export interface BacktestRun {
  run_id: string;
  started_at: string;
  completed_at: string;
  date_from: string;
  date_to: string;
  total_signals: number;
  wins: number;
  losses: number;
  expired: number;
  total_pnl: number;
  win_rate: number;
  status: string;
}

