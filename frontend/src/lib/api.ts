/** Same-origin API client. Exchange credentials never enter browser storage. */
let workspaceToken = sessionStorage.getItem('sibyl-token') ?? '';

export function setToken(value: string) {
  workspaceToken = value;
  if (value) sessionStorage.setItem('sibyl-token', value);
  else sessionStorage.removeItem('sibyl-token');
  window.dispatchEvent(new Event('sibyl-refresh'));
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(workspaceToken ? { Authorization: `Bearer ${workspaceToken}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') message = body.detail;
      else if (Array.isArray(body.detail))
        message = body.detail.map((error: { msg: string }) => error.msg).join(' ');
    } catch {
      /* An upstream server may return non-JSON errors. */
    }
    throw new Error(message);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  });
export const refresh = () => window.dispatchEvent(new Event('sibyl-refresh'));
export const money = (value: number, digits = 2) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
export const number = (value: number, digits = 2) =>
  new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }).format(value);
export const percent = (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
export const shortDate = (value: string) =>
  new Date(value).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
  });

export function exportCSV(filename: string, rows: (string | number)[][]) {
  // Quote fields and neutralize spreadsheet formula prefixes in untrusted labels.
  const csv = rows
    .map((row) =>
      row
        .map((value) => {
          const text = String(value);
          return `"${(/^[=+@\-]/.test(text) && typeof value === 'string' ? "'" : '') + text.replaceAll('"', '""')}"`;
        })
        .join(','),
    )
    .join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Download authenticated same-origin exports without putting the workspace token in a URL. */
export async function downloadFile(path: string, filename: string) {
  const response = await fetch(`/api/v1${path}`, {
    headers: workspaceToken ? { Authorization: `Bearer ${workspaceToken}` } : {},
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === 'string' ? body.detail : `Download failed (${response.status}).`,
    );
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
