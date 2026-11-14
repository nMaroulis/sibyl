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
  demo: {
    txid: string;
    address: string;
    block_height: number;
    confirmed_spend_txid: string;
    pending_spend_txid: string;
  };
};

export type BitcoinOutputSpends = BitcoinAttribution & {
  kind: 'output_spends';
  transaction_id: string;
  output_offset: number;
  parent_status: BitcoinStatus;
  total: number;
  limit: number;
  next_offset: number | null;
  spend_note: string;
  items: (BitcoinOutput & {
    spent: boolean;
    state: 'unspent' | 'pending' | 'confirmed' | 'unknown';
    spending_txid: string | null;
    spending_input_index: number | null;
    status: BitcoinStatus | null;
    reason: string | null;
  })[];
};

export const bitcoinSpendLabel = {
  confirmed: 'Spent · confirmed',
  pending: 'Spend pending',
  unspent: 'No spend reported',
  unknown: 'Spend details unknown',
} as const;

export type BitcoinWatchObservation = {
  observed_at: string;
  value_sats: number;
  state: Exclude<keyof typeof bitcoinSpendLabel, 'unknown'>;
  spending_txid: string | null;
  spending_input_index: number | null;
  spending_block_hash: string | null;
  spending_block_height: number | null;
  parent_block_hash: string | null;
  parent_block_height: number | null;
};

export type BitcoinWatch = {
  id: string;
  transaction_id: string;
  output_index: number;
  demo: boolean;
  active: boolean;
  revision: number;
  next_check: string | null;
  error: string | null;
  observation: BitcoinWatchObservation | null;
};

export type BitcoinWatchList = {
  items: BitcoinWatch[];
  limit: number;
  recovery_required: boolean;
};

export const bitcoinWatchURL = (id: string) =>
  `/research?tab=explorer&watch=${encodeURIComponent(id)}`;

export type BitcoinBlockReport = {
  kind: 'block';
  source: string;
  network: string;
  observed_at: string;
  in_best_chain: boolean | null;
  block: {
    id: string;
    height: number;
    timestamp: number;
    tx_count: number;
    size: number;
    weight: number;
    parent_hash: string | null;
  };
  transaction_offset: number;
  next_offset: number | null;
  items: {
    index: number;
    txid: string;
    coinbase: boolean;
    fee_sats: number;
    input_count: number;
    output_count: number;
  }[];
  url: string | null;
  note: string;
};
