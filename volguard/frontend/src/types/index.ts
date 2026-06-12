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
  confidence_score: number;
  gates_passed: number;
  system_status: SystemStatus;
  market_state: MarketState;
  dce: GateResult;
  signal: Signal;
}
