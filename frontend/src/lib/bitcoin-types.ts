export type BitcoinStatus = {
  confirmed: boolean;
  confirmations: number | null;
  block_height: number | null;
  block_hash: string | null;
  block_time: number | null;
};
export type BitcoinOutput = {
  index: number;
  value_sats: number;
  address: string | null;
  script_type: string;
};
export type BitcoinTransaction = {
  txid: string;
  status: BitcoinStatus;
  version: number;
  locktime: number;
  size: number;
  weight: number;
  vsize: number;
  fee_sats: number;
  fee_rate_sat_vb: number;
  coinbase: boolean;
  input_count: number;
  output_count: number;
  missing_prevouts: number;
  input_total_sats: number | null;
  output_total_sats: number;
  inputs: {
    index: number;
    coinbase: boolean;
    txid: string | null;
    vout: number | null;
    previous_output: BitcoinOutput | null;
  }[];
  outputs: BitcoinOutput[];
  input_offset: number;
  output_offset: number;
  next_input_offset: number | null;
  next_output_offset: number | null;
};
export type BitcoinActivity = {
  txid: string;
  status: BitcoinStatus;
  fee_sats: number;
  fee_rate_sat_vb: number;
  received_sats: number;
  spent_sats: number | null;
  net_sats: number | null;
  input_count: number;
  output_count: number;
};
export type BitcoinHistory = {
  items: BitcoinActivity[];
  cursor: string | null;
  next_cursor: string | null;
  pending: boolean;
  limit: number;
  truncation_possible: boolean;
};
export type BitcoinStats = {
  tx_count: number;
  funded_txo_count: number;
  funded_txo_sum: string;
  spent_txo_count: number;
  spent_txo_sum: string;
};
export type BitcoinAttribution = {
  source: string;
  network: string;
  observed_at: string;
  tip_height: number | null;
  warnings: string[];
  note: string;
};
export type BitcoinReport = BitcoinAttribution & { url: string | null } & (
    | { kind: 'transaction'; transaction: BitcoinTransaction }
    | {
        kind: 'address';
        address: {
          address: string;
          chain_stats: BitcoinStats;
          mempool_stats: BitcoinStats;
          confirmed_balance_sats: number;
          pending_delta_sats: number;
          projected_balance_sats: number | null;
        };
        history: BitcoinHistory;
      }
  );
export type BitcoinCapabilities = {
  network: string;
  source: string;
  source_url: string;
  note: string;
  demo: { txid: string; address: string };
};
