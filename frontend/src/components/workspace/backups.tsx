import { useState } from 'react';
import { Download, FolderArchive, LockKeyhole, ShieldCheck, Trash2, Upload } from 'lucide-react';
import { api, downloadFile, post, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { Badge, Empty, ErrorState, Loading, Modal, Panel, PanelTitle, useToast } from '../ui';

type Backup = { id: string; bytes: number; created_at: string };
type Inspection = {
  sibyl: string;
  created_at: string;
  files: number;
  unpacked_bytes: number;
  restore_mode: string;
};
type Restored = { data_dir: string; note: string };
const size = (bytes: number) =>
  bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(1)} KiB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MiB`;

/** Encrypted archives stay local; recovery never replaces the active workspace. */
export function WorkspaceBackups() {
  const catalog = useResource<{ items: Backup[]; scope: string }>('/workspace/backups');
  const [mode, setMode] = useState<'create' | 'inspect' | 'remove'>();
  const [selected, setSelected] = useState<Backup>();
  const [passphrase, setPassphrase] = useState('');
  const [repeat, setRepeat] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [inspection, setInspection] = useState<Inspection>();
  const [restored, setRestored] = useState<Restored>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const close = () => {
    if (busy) return;
    setMode(undefined);
    setSelected(undefined);
    setPassphrase('');
    setRepeat('');
    setInspection(undefined);
    setError('');
    setConfirmation('');
  };
  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try {
      await action();
      refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel>
      <PanelTitle
        title="Workspace backups"
        subtitle="Encrypted snapshots · portable copies · separate recovery"
        action={
          <button
            className="button primary"
            onClick={() => {
              close();
              setMode('create');
            }}
          >
            <FolderArchive size={16} /> Create backup
          </button>
        }
      />
      <div className="backup-security">
        <LockKeyhole size={21} />
        <p>
          Backups contain your databases, research files and vault key inside passphrase-protected
          encryption. Keep the passphrase separately; Sibyl does not store it and cannot recover it.
        </p>
        <Badge>Encrypted</Badge>
      </div>
      {catalog.error ? (
        <ErrorState message={catalog.error} retry={catalog.retry} />
      ) : catalog.loading ? (
        <Loading />
      ) : !catalog.data?.items.length ? (
        <Empty title="Keep a recoverable copy">
          Create a local archive, download an extra copy, and inspect it to verify your passphrase
          before relying on it.
        </Empty>
      ) : (
        <div className="backup-list">
          {catalog.data.items.map((item) => (
            <article key={item.id}>
              <FolderArchive size={22} />
              <div>
                <h3>{new Date(item.created_at).toLocaleString()}</h3>
                <p>
                  {size(item.bytes)} · {item.id.slice(0, 8)}
                </p>
              </div>
              <button
                className="button small"
                disabled={busy}
                onClick={() => {
                  close();
                  setSelected(item);
                  setMode('inspect');
                }}
              >
                Inspect / restore
              </button>
              <button
                className="icon-button"
                aria-label="Download encrypted backup"
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    await downloadFile(
                      `/workspace/backups/${item.id}/download`,
                      `sibyl-${item.id}.sibylbackup`,
                    );
                  })
                }
              >
                <Download size={16} />
              </button>
              <button
                className="icon-button"
                aria-label="Remove local backup"
                disabled={busy}
                onClick={() => {
                  close();
                  setSelected(item);
                  setMode('remove');
                }}
              >
                <Trash2 size={16} />
              </button>
            </article>
          ))}
        </div>
      )}
      <label className="backup-upload button">
        <Upload size={15} /> Import an encrypted backup
        <input
          aria-label="Import an encrypted backup"
          type="file"
          accept=".sibylbackup"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            event.target.value = '';
            if (file.size > 384 * 1024 * 1024) {
              setError('Choose an archive up to 384 MiB.');
              return;
            }
            run(async () => {
              const item = await api<Backup>('/workspace/backups/upload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/octet-stream' },
                body: file,
              });
              setSelected(item);
              setMode('inspect');
              toast('Encrypted archive imported. Inspect it with its passphrase.');
            });
          }}
        />
      </label>
      {error && !mode && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <p className="footnote">
        {catalog.data?.scope} Archives exclude environment files outside the workspace and installed
        model weights. Downloaded copies and restored directories are independent of this list.
      </p>
      {mode && (
        <Modal
          title={
            mode === 'create'
              ? 'Create an encrypted backup'
              : mode === 'remove'
                ? 'Remove this local backup?'
                : 'Inspect and restore'
          }
          onClose={close}
        >
          {mode === 'remove' ? (
            <>
              <p>
                Remove this encrypted archive from this machine. Downloaded copies and restored
                workspaces are unaffected.
              </p>
              <div className="dialog-actions">
                <button className="button" disabled={busy} onClick={close}>
                  Keep backup
                </button>
                <button
                  className="button primary"
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      await api(`/workspace/backups/${selected?.id}`, { method: 'DELETE' });
                      setMode(undefined);
                      toast('Local archive removed.');
                    })
                  }
                >
                  Remove local backup
                </button>
              </div>
            </>
          ) : (
            <div className="workspace-form">
              <label>
                {mode === 'create' ? 'New backup passphrase' : 'Archive passphrase'}
                <input
                  autoComplete={mode === 'create' ? 'new-password' : 'off'}
                  type="password"
                  value={passphrase}
                  minLength={12}
                  maxLength={1024}
                  onChange={(event) => {
                    setPassphrase(event.target.value);
                    setInspection(undefined);
                  }}
                />
              </label>
              {mode === 'create' ? (
                <>
                  <label>
                    Confirm passphrase
                    <input
                      type="password"
                      autoComplete="new-password"
                      value={repeat}
                      onChange={(event) => setRepeat(event.target.value)}
                    />
                  </label>
                  <p className="footnote">
                    At least twelve characters. Save this passphrase somewhere separate from the
                    archive. The vault key is included inside encryption.
                  </p>
                  <button
                    className="button primary"
                    disabled={busy || passphrase.length < 12 || passphrase !== repeat}
                    onClick={() =>
                      run(async () => {
                        await post('/workspace/backups', { passphrase });
                        setPassphrase('');
                        setRepeat('');
                        setMode(undefined);
                        toast('Encrypted backup saved locally. Download a copy for safekeeping.');
                      })
                    }
                  >
                    {busy ? 'Creating snapshot and encrypting…' : 'Create encrypted backup'}
                  </button>
                </>
              ) : (
                <>
                  <button
                    className="button"
                    disabled={busy || passphrase.length < 12}
                    onClick={() =>
                      run(async () => {
                        setInspection(
                          await post<Inspection>(`/workspace/backups/${selected?.id}/inspect`, {
                            passphrase,
                          }),
                        );
                      })
                    }
                  >
                    {busy ? 'Validating…' : 'Inspect archive'}
                  </button>
                  {inspection && (
                    <div className="backup-inspection">
                      <ShieldCheck size={23} />
                      <div>
                        <h3>Authenticated archive · Sibyl {inspection.sibyl}</h3>
                        <p>
                          {inspection.files} files · {size(inspection.unpacked_bytes)} unpacked ·{' '}
                          {new Date(inspection.created_at).toLocaleString()}
                        </p>
                        <p>{inspection.restore_mode}</p>
                      </div>
                    </div>
                  )}
                  {inspection && (
                    <>
                      <p>
                        Restore creates a new directory. Your running workspace stays in place. The
                        recovered copy starts with automatic work paused and accounts inactive, so
                        you can review exchange orders, strategies, schedules and messaging first.
                      </p>
                      <label>
                        Type RESTORE AS NEW WORKSPACE
                        <input
                          value={confirmation}
                          autoComplete="off"
                          onChange={(event) => setConfirmation(event.target.value)}
                        />
                      </label>
                      <button
                        className="button primary"
                        disabled={busy || confirmation !== 'RESTORE AS NEW WORKSPACE'}
                        onClick={() =>
                          run(async () => {
                            setRestored(
                              await post<Restored>(`/workspace/backups/${selected?.id}/restore`, {
                                passphrase,
                                confirmation,
                              }),
                            );
                            setPassphrase('');
                            setInspection(undefined);
                            setMode(undefined);
                          })
                        }
                      >
                        {busy ? 'Restoring and validating…' : 'Restore as a new workspace'}
                      </button>
                    </>
                  )}
                </>
              )}
            </div>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
        </Modal>
      )}
      {restored && (
        <Modal
          title="Recovered workspace is ready for review"
          onClose={() => setRestored(undefined)}
        >
          <div className="workspace-form">
            <p>{restored.note}</p>
            <label>
              Recovered data directory
              <input
                value={restored.data_dir}
                readOnly
                onFocus={(event) => event.target.select()}
              />
            </label>
            <button
              className="button"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(restored.data_dir);
                  toast('Directory copied.');
                } catch {
                  toast('Select and copy the directory manually.');
                }
              }}
            >
              Copy directory
            </button>
            <p className="footnote">
              Launch Sibyl with its <code>--data-dir</code> option pointing to this directory. Use a
              different port if the current workspace is still running. Workspace settings in the
              recovered app guide the final review.
            </p>
          </div>
        </Modal>
      )}
    </Panel>
  );
}
