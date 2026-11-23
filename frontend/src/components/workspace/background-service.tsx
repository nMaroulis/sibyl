import { useState } from 'react';
import { Copy, RefreshCw, ServerCog } from 'lucide-react';
import { Badge, ErrorState, Panel, useToast } from '../ui';
import { useResource } from '../../lib/hooks';
import { DOCUMENTATION_URL } from '../../lib/docs';

type ServiceState = {
  supported: boolean;
  available: boolean;
  installed?: boolean | null;
  owned?: boolean;
  configuration_valid?: boolean;
  state: string;
  platform?: string;
  name?: string;
  running: boolean;
  registered?: boolean | null;
  enabled?: boolean | null;
  pid?: number | null;
  last_exit_code?: number | null;
  last_task_result?: number | null;
  this_process?: boolean | null;
  workspace_matches?: boolean | null;
  log_file?: string | null;
  note: string;
  commands?: Record<
    'preview' | 'install' | 'status' | 'start' | 'stop' | 'restart' | 'uninstall',
    string
  >;
};

/** Native status is loaded only when expanded; commands are copied, never executed by the page. */
export function BackgroundService() {
  const [open, setOpen] = useState(false);
  const state = useResource<ServiceState>('/workspace/service', 0, open);
  const toast = useToast();
  const data = state.data;
  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast('Command copied. Run it deliberately in a local terminal.');
    } catch {
      toast('Copy the command text manually.', true);
    }
  };
  return (
    <Panel className="workspace-health background-service">
      <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
        <summary>
          <ServerCog size={18} aria-hidden="true" />
          <div>
            <strong>Background service</strong>
            <span>Start Sibyl at login · native user-level service</span>
          </div>
          <Badge>{data?.running ? 'OS reports running' : 'Local install'}</Badge>
        </summary>
        {open && (
          <div className="background-service-body">
            {state.error && <ErrorState message={state.error} retry={state.retry} />}
            {state.loading && <p role="status">Reading the user-service manager…</p>}
            {data && (
              <>
                <div className="inline-badges">
                  <Badge tone={data.running ? 'lime' : 'lavender'}>
                    {data.state.replaceAll('_', ' ')}
                  </Badge>
                  {data.platform && <Badge>{data.platform}</Badge>}
                  {data.pid && <Badge>PID {data.pid}</Badge>}
                  {data.this_process === true && <Badge>This backend process</Badge>}
                </div>
                <p className="footnote">
                  OS status describes the registered service. A manually started backend can be
                  separate; running does not establish HTTP readiness or completed background work.
                </p>
                {data.installed && !data.owned && (
                  <p className="form-error">
                    This definition could not be verified as Sibyl-managed. No automatic replacement
                    or control is available.
                  </p>
                )}
                {data.workspace_matches === false && (
                  <p className="form-error">
                    The registered service points to a different workspace.
                  </p>
                )}
                {data.installed && !data.configuration_valid && (
                  <p className="footnote">
                    The launch definition/receipt is missing or changed. Stop and inspect it before
                    reinstalling explicitly.
                  </p>
                )}
                {!data.available && (
                  <p className="footnote">
                    A user-service manager could not be reached in this session. Foreground startup
                    and Docker remain available.
                  </p>
                )}
                {data.log_file && (
                  <p className="footnote">
                    Private rotating backend log: <code>{data.log_file}</code>
                  </p>
                )}
                {data.last_exit_code != null && (
                  <p className="footnote">Last process exit code: {data.last_exit_code}</p>
                )}
                {data.last_task_result != null && (
                  <p className="footnote">
                    Last Task Scheduler result: {data.last_task_result} · this can be a scheduler
                    status rather than a process exit code.
                  </p>
                )}
                {data.commands && (
                  <div className="background-service-commands">
                    <strong>Run in your local terminal</strong>
                    <p className="footnote">
                      Preview first, install for future logins, then start explicitly. If this port
                      is already used by a manual server, stop that server first. Add an explicit{' '}
                      <code>--env-file</code> path to install if needed; shell-only values are not
                      copied.
                    </p>
                    {(
                      [
                        'preview',
                        data.installed ? 'status' : 'install',
                        'start',
                        'stop',
                        'uninstall',
                      ] as const
                    ).map((action) => (
                      <div className="service-command" key={action}>
                        <span>{action}</span>
                        <code>{data.commands![action]}</code>
                        <button
                          className="icon-button"
                          type="button"
                          aria-label={`Copy service ${action} command`}
                          onClick={() => void copy(data.commands![action])}
                        >
                          <Copy size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <p className="footnote">
                  Stop disables future login starts until Start is used again. Windows tasks require
                  a signed-in user and may stop abruptly. Uninstall keeps databases, keys, backups
                  and logs. Service controls do not undo venue orders or messages.
                </p>
                <div className="workspace-actions">
                  <button className="text-button" onClick={state.retry}>
                    <RefreshCw size={13} /> Refresh OS status
                  </button>
                  <a
                    className="text-link"
                    href={`${DOCUMENTATION_URL}guides/background-service/`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Service setup guide ↗
                  </a>
                </div>
              </>
            )}
          </div>
        )}
      </details>
    </Panel>
  );
}
