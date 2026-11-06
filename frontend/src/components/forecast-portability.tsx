import { useState } from 'react';
import { Archive, Download, Upload } from 'lucide-react';
import { api, downloadFile, post } from '../lib/api';
import type { ForecastDetail, ForecastModel } from '../lib/forecast-types';
import { Panel, useToast } from './ui';

/** Explicit offline imports never trust the uploaded model's claimed fit or provider origin. */
export function ForecastPortability({
  model,
  showArchived,
  setShowArchived,
  changed,
}: {
  model?: ForecastModel;
  showArchived: boolean;
  setShowArchived: (value: boolean) => void;
  changed: (id?: string) => void;
}) {
  const [file, setFile] = useState<File>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const action = async (kind: 'import' | 'export' | 'archive') => {
    setBusy(true);
    setError('');
    try {
      if (kind === 'import' && file) {
        if (file.size > 16 * 1024 * 1024)
          throw new Error('Choose a JSON bundle no larger than 16 MiB.');
        const result = await api<ForecastDetail & { import_result: { duplicate: boolean } }>(
          '/forecast-models/import',
          {
            method: 'POST',
            body: file,
            headers: { 'Content-Type': 'application/octet-stream' },
          },
        );
        setShowArchived(true);
        changed(result.model.id);
        setFile(undefined);
        toast(
          result.import_result.duplicate
            ? 'This bundle is already imported.'
            : 'Recipe verified and refitted locally. Imported source remains unverified.',
        );
      } else if (kind === 'export' && model) {
        await downloadFile(
          `/forecast-models/${model.id}/bundle`,
          `chronos-bundle-${model.id}.json`,
        );
      } else if (kind === 'archive' && model) {
        await post(`/forecast-models/${model.id}/archive`, {
          archived: !model.archived,
          revision: model.archive_revision ?? 0,
        });
        setShowArchived(true);
        changed(model.id);
        toast(
          model.archived
            ? 'Model restored.'
            : 'Model archived. Saved results and outcome monitors are retained.',
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel className="research-transfer">
      <div className="research-transfer-heading">
        <strong>Model library</strong>
        <label className="inline-check">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
          />
          Show archived versions
        </label>
      </div>
      <div className="forecast-workspace-actions">
        {model && (
          <>
            <button className="text-button" disabled={busy} onClick={() => void action('export')}>
              <Download size={14} />
              Export portable bundle
            </button>
            <button className="text-button" disabled={busy} onClick={() => void action('archive')}>
              <Archive size={14} />
              {model.archived ? 'Restore model' : 'Archive model'}
            </button>
          </>
        )}
      </div>
      <details>
        <summary>Import a model from another workspace</summary>
        <p className="footnote">
          Portable JSON includes the recipe and complete training input. Sibyl verifies its
          integrity and refits locally. Provider origin stays unverified; saved forecasts and live
          outcome tracking are not imported. Maximum 16 MiB.
        </p>
        <div className="forecast-workspace-actions">
          <label>
            Forecast bundle
            <input
              aria-label="Forecast bundle"
              type="file"
              accept=".json,application/json"
              disabled={busy}
              onChange={(e) => setFile(e.target.files?.[0])}
            />
          </label>
          <button
            className="button secondary"
            disabled={busy || !file}
            onClick={() => void action('import')}
          >
            <Upload size={14} />
            {busy ? 'Working…' : 'Import & verify'}
          </button>
        </div>
      </details>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </Panel>
  );
}
