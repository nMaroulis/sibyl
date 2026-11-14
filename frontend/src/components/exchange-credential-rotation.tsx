import { useState } from 'react';
import type { FormEvent } from 'react';
import { KeyRound, Power } from 'lucide-react';
import { api, post, refresh } from '../lib/api';
import { useResource } from '../lib/hooks';
import type { Connection, ExchangeProvider } from '../lib/types';
import { SecretField } from './secret-field';
import { ErrorState, Loading, Modal, useToast } from './ui';

type Status = { id: string; active: boolean; revision: string; confirmation: string; note: string };

/** Replace a complete same-account credential set; saved secrets are never read into the form. */
export function ExchangeCredentialRotation({
  connection,
  provider,
  onClose,
  onSaved,
}: {
  connection: Connection;
  provider: ExchangeProvider;
  onClose: () => void;
  onSaved: () => void;
}) {
  const state = useResource<Status>(`/connections/${connection.id}/credentials/status`);
  const [apiKey, setApiKey] = useState(''),
    [secret, setSecret] = useState(''),
    [passphrase, setPassphrase] = useState(''),
    [uid, setUid] = useState('');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const toast = useToast();
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!state.data) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError('');
    try {
      await api(`/connections/${connection.id}/credentials`, {
        method: 'PUT',
        body: JSON.stringify({
          api_key: apiKey.trim(),
          secret: secret.trim(),
          passphrase,
          uid,
          revision: state.data.revision,
          confirmation: form.get('confirmation'),
          same_account: form.get('same_account') === 'on',
        }),
      });
      setApiKey('');
      setSecret('');
      setPassphrase('');
      setUid('');
      toast('New credentials encrypted. Check access, then activate this account when ready.');
      refresh();
      onSaved();
    } catch (reason) {
      setError((reason as Error).message);
      state.retry();
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={`Update keys · ${connection.label}`} onClose={onClose}>
      {state.loading && <Loading />}
      {state.error && <ErrorState message={state.error} retry={state.retry} />}
      {state.data && (
        <>
          <p className="muted">{state.data.note}</p>
          <p className="footnote">
            Existing venue orders and holdings remain at the exchange. This action does not cancel
            them. Use replacement keys for the same trading wallet, subaccount and API environment.
          </p>
          {state.data.active ? (
            <div className="form-callout">
              <p>
                Deactivate this connection before changing its keys. This pauses inclusion/imports
                and prevents new account-bound strategy admission; it does not cancel existing
                exchange orders.
              </p>
              <button
                className="button secondary"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await post(`/connections/${connection.id}/activation`, { active: false });
                    refresh();
                    state.retry();
                  } catch (reason) {
                    setError((reason as Error).message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <Power size={14} />
                Deactivate connection
              </button>
            </div>
          ) : (
            <form className="form" onSubmit={save}>
              <SecretField
                label={provider.id === 'coinbase' ? 'CDP API key name' : 'New API key'}
                value={apiKey}
                onChange={setApiKey}
              />
              <SecretField
                label={provider.id === 'coinbase' ? 'New private key (PEM)' : 'New API secret'}
                value={secret}
                onChange={setSecret}
                multiline={provider.id === 'coinbase'}
              />
              {provider.passphrase && (
                <SecretField label="API passphrase" value={passphrase} onChange={setPassphrase} />
              )}
              {provider.uid && <SecretField label="API memo" value={uid} onChange={setUid} />}
              <label className="checkbox-label">
                <input name="same_account" type="checkbox" required />
                These keys belong to the same exchange account and wallet as this connection.
              </label>
              <label>
                Type {state.data.confirmation}
                <input name="confirmation" autoComplete="off" required />
              </label>
              <button
                className="button"
                type="submit"
                disabled={busy || !apiKey.trim() || !secret.trim()}
              >
                <KeyRound size={14} />
                {busy ? 'Saving…' : 'Replace saved credentials'}
              </button>
            </form>
          )}
        </>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </Modal>
  );
}
