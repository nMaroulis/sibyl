import { useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { number, post } from '../lib/api';
import { Badge } from './ui';
import './bitcoin-output-spends.css';

type Proof = {
  verified: boolean;
  header_matches: boolean;
  root_matches: boolean;
  block_height: number;
  position: number;
  block_hash: string;
  header_hash: string;
  header_merkle_root: string;
  calculated_merkle_root: string;
  observed_at: string;
};

export function BitcoinInclusionProof({
  transactionId,
  blockHash,
  demo,
}: {
  transactionId: string;
  blockHash: string;
  demo: boolean;
}) {
  const [proof, setProof] = useState<Proof>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const verify = async () => {
    setBusy(true);
    setProof(undefined);
    setError('');
    try {
      setProof(
        await post<Proof>('/bitcoin/inclusion-proof', {
          transaction_id: transactionId,
          block_hash: blockHash,
          demo,
        }),
      );
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="bitcoin-spends" aria-label="Transaction inclusion proof">
      <div className="bitcoin-spends-heading">
        <strong>Transaction inclusion proof</strong>
        <button className="text-button" disabled={busy} onClick={() => void verify()}>
          <ShieldCheck size={14} aria-hidden="true" />
          {busy ? 'Checking proof…' : proof ? 'Check again' : 'Verify inclusion'}
        </button>
      </div>
      <p className="footnote">
        {demo ? 'Synthetic block. ' : ''}
        Checks the transaction against the selected block header. Best-chain status comes from a
        separate indexer observation.
      </p>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {proof && (
        <details className="bitcoin-proof-result">
          <summary>
            <Badge tone={proof.verified ? 'green' : 'amber'}>
              {proof.verified ? 'Inclusion verified against header' : 'Proof did not match'}
            </Badge>
          </summary>
          <p className="footnote">
            Block #{number(proof.block_height, 0)} · transaction index {number(proof.position, 0)}
            {' · '}
            {new Date(proof.observed_at).toLocaleString()}
          </p>
          <dl>
            <dt>
              {proof.header_matches ? 'Block header hash matches' : 'Block header hash differs'}
            </dt>
            <dd>
              <code>{proof.header_hash}</code>
            </dd>
            <dt>Merkle root in header</dt>
            <dd>
              <code>{proof.header_merkle_root}</code>
            </dd>
            {!proof.root_matches && (
              <>
                <dt>Calculated Merkle root</dt>
                <dd>
                  <code>{proof.calculated_merkle_root}</code>
                </dd>
              </>
            )}
          </dl>
        </details>
      )}
    </section>
  );
}
