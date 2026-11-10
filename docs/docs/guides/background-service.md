---
title: Run Sibyl in the background
description: Native user-login services with explicit CLI controls, private logs and read-only status.
---

# Run Sibyl in the background

A user service keeps Sibyl independent of your terminal and starts it at future logins. Install the same Python package/environment first and build the dashboard when using a source checkout. No administrator/root service or account password is installed. This does not install Python, Ollama, packages or exchange connections for you.

| Platform | Native manager | Scope |
| --- | --- | --- |
| macOS | launchd LaunchAgent | Your GUI login session. |
| Linux | systemd user unit | Your user manager/login; no automatic lingering or boot-time system unit. |
| Windows | Task Scheduler | Your signed-in user's interactive token, with a SID-specific task name. No password is stored. |

## Preview, install, then start

Open **Settings → Workspace → Background service**. Expanding this panel reads OS status and shows commands tailored to the current backend's Python environment, workspace and port. Copy commands to a local terminal; the page and AI agents never execute service changes.

```bash
sibyl service preview --data-dir /absolute/path/to/workspace
sibyl service install --data-dir /absolute/path/to/workspace
sibyl service start
sibyl service status
```

Use your actual workspace path, including its databases and vault key. The panel's commands include the interpreter path, so they also work when the `sibyl` command is not on your terminal's PATH. `uv run sibyl service …` works from a checkout. Preview prints the exact definition and launch choices without writing or registering anything. **Install registers future-login startup without starting the app now.** Start is deliberate and refuses an already occupied port rather than killing a manual server.

The service binds to `127.0.0.1`. Add `--port 8123` to preview/install for a different unprivileged port. An optional `--dashboard-dir` selects an existing build. The installed Python environment must remain available at its recorded absolute path; a temporary `uvx` environment is unsuitable for a persistent service.

### Private configuration

Service definitions contain paths and nonsecret launch flags, never copies of shell environment values or API keys. Saved encrypted workspace credentials keep working. Shell-only variables and an implicit `.env` in your old terminal directory are **not copied**.

If you require environment-file settings, pass the private file's absolute path explicitly:

```bash
sibyl service install --data-dir /absolute/path/to/workspace --env-file /absolute/path/to/private.env
```

The process reads that file directly. Protect it yourself; its contents are not moved into the service definition. CLI workspace, loopback host and port choices take precedence. Existing execution/recovery permissions still apply; service installation does not activate accounts, approve trades or start Ollama.

## Stop, restart and remove

```bash
sibyl service stop
sibyl service start
sibyl service restart
sibyl service uninstall
```

**Stop also disables future login starts**, until Start enables them again. Restart stops then starts; if shutdown is still in progress or the port is occupied, it fails visibly instead of claiming a restart. Inspect status and start deliberately after shutdown. Uninstall removes the verified managed startup files/registration and retains databases, credentials, backups and logs. Unmanaged definitions with matching names and terminal symlinks are not replaced.

After moving/upgrading the recorded Python environment, stop the service, preview from the new environment, then use `install --replace` with the same workspace and desired launch options. Replacing a running service is rejected. An identical installation is idempotent; it does not silently restart a process. An OS error/timeout can leave a definition or accepted native request to inspect; commands are not automatically retried or blindly rolled back.

:::note[Stopping is not an undo]

Use the app's automation controls before planned shutdown where appropriate. Stopping a process does not cancel venue orders, undo sent messages or establish that an uncertain operation failed. macOS/Linux receive native termination handling. Windows Task Scheduler can terminate the task abruptly; inspect existing recovery/reconciliation state on restart.

:::

## Understand status and logs

Native **running** means the OS reports a running service, not that `/health`, agents, external providers or background jobs are ready. The backend currently open in your browser might have been launched manually or belong to another workspace. The panel shows workspace mismatch, observed PID/current-process matching where available, and native last-result fields. Windows task results can be scheduler codes rather than process exit codes; its task interface does not supply an app PID here. An unavailable manager is reported as unavailable, never as verified absence.

Backend logs live in `<workspace>/service-logs/sibyl.log`, with three retained 5 MiB rotations. HTTP access/query logging is disabled for service launches. Log files use restrictive local permissions where supported; they can still contain operational error details, so review them before sharing. The root logger stays at warning level. Service control never downloads or sends logs to an agent.

If startup fails, inspect OS status and that file, then run the launch choices from `service preview` in your foreground terminal for configuration errors occurring before logging starts. Windows uses the environment's sibling `pythonw.exe` where available to avoid a console window. Linux/macOS failed-exit restart policies and Windows failure retries are native-manager behavior, not task/order replay.

SSH-only macOS sessions, Linux containers without a user systemd bus, locked-down Windows task policies and platform-specific permissions can prevent service management. Foreground startup and Docker remain available. Native command/schema contracts and isolated process startup are tested; broader real OS login/logout, upgrade and outage acceptance remain in the planning checklist.
