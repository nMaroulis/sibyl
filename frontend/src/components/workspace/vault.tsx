import { useState } from 'react';
import type { FormEvent } from 'react';
import { KeyRound, RotateCw, ShieldCheck } from 'lucide-react';
import { post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { Badge, ErrorState, Modal, Panel, PanelTitle, useToast } from '../ui';

type Vault = {
  key_id: string;
  recovery_pending: boolean;
  confirmation: string;
  record_counts: Record<string, number>;
  history: { id: number; at: string; key_id: string; records: number; recovered: number }[];
  note: string;
};

/** Keys remain backend-only. Rotation is an explicit local wrapping operation, not provider revocation. */
export function WorkspaceVault() {
  const state = useResource<Vault>('/workspace/vault');
  const [editing, setEditing] = useState(false),
    [busy, setBusy] = useState(false);
  const toast = useToast();
  const rotate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!state.data) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await post('/workspace/vault/rotate', {
        key_id: state.data.key_id,
        confirmation: String(form.get('confirmation')),
      });
      setEditing(false);
      refresh();
      toast('Local vault key rotated. Provider credentials and account history were preserved. Review credential-bound funding sync controls before re-enabling them.');
    } catch (error) {
      toast((error as Error).message, true);
      state.retry();
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel className="workspace-health">
      <PanelTitle
        title="Credential vault"
        subtitle="Local encryption · audited key rotation"
        action={<ShieldCheck size={18} />}
      />
      {state.error && <ErrorState message={state.error} retry={state.retry} />}
      {state.data && (
        <>
          <p className="footnote">{state.data.note}</p>
          <div className="inline-badges">
            <Badge tone={state.data.recovery_pending ? 'amber' : 'lime'}>
              {state.data.recovery_pending ? 'Rotation needs completion' : 'Encrypted locally'}
            </Badge>
            <span className="footnote">Key ID {state.data.key_id}</span>
          </div>
          {state.data.recovery_pending && (
            <p role="status">
              A previous wrapping key is retained for interruption recovery. Complete rotation
              before making a new backup or removing any vault files.
            </p>
          )}
          <button className="button secondary" onClick={() => setEditing(true)}>
            <KeyRound size={14} />
            {state.data.recovery_pending ? 'Complete rotation' : 'Rotate local vault key'}
          </button>
          {state.data.history.length > 0 && (
            <details>
              <summary>Rotation history · {state.data.history.length} retained entries</summary>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Completed</th>
                      <th>Key ID</th>
                      <th>Re-encrypted records</th>
                      <th>Recovery</th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.data.history.map((row) => (
                      <tr key={row.id}>
                        <td>{new Date(row.at).toLocaleString()}</td>
                        <td>{row.key_id}</td>
                        <td>{row.records}</td>
                        <td>{row.recovered ? 'Completed interrupted rotation' : 'New rotation'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </>
      )}
      {editing && state.data && (
        <Modal
          title={
            state.data.recovery_pending ? 'Complete local key rotation' : 'Rotate local vault key'
          }
          onClose={() => setEditing(false)}
        >
          <form className="form-grid" onSubmit={rotate}>
            <p>
              Saved exchange credentials, AI profiles and encrypted settings will be re-encrypted. A
              recovery key is retained until the database commit succeeds.
            </p>
            <p className="footnote">
              This does not revoke API tokens at any provider. Existing encrypted backups contain
              their original matching vault keys. Keep a private backup before changing your
              encryption setup.
            </p>
            <label>
              Type {state.data.confirmation}
              <input name="confirmation" autoComplete="off" required />
            </label>
            <button className="button" type="submit" disabled={busy}>
              <RotateCw size={14} />
              {busy ? 'Re-encrypting…' : 'Rotate and retain audit'}
            </button>
          </form>
        </Modal>
      )}
    </Panel>
  );
}
