import { useState } from 'react';
import { FileText, Image, Mic, LoaderCircle, Check, ArrowUpRight } from 'lucide-react';
import { api, refresh } from '../../lib/api';
import { useResource } from '../../lib/hooks';
import { Badge, ErrorState, Loading, useToast } from '../ui';

type MediaState = {
  documents: boolean;
  photos: boolean;
  audio: boolean;
  ocr_language: string;
  audio_language: string;
  has_model: boolean;
  model_name: string | null;
  ready: Record<'documents' | 'photos' | 'audio', boolean>;
  dependencies: { tesseract: boolean; ffmpeg: boolean; whisper: boolean; model: boolean };
  note: string;
};

/** Make attachment retention a separate opt-in; presence checks do not verify model quality. */
export function TelegramAttachments() {
  const resource = useResource<MediaState>('/settings/messaging/telegram/attachments');
  return (
    <details className="telegram-attachments">
      <summary>
        <FileText size={15} /> Telegram attachments <span>Optional · saved in My research</span>
      </summary>
      {resource.loading ? (
        <Loading />
      ) : resource.error ? (
        <ErrorState message={resource.error} retry={resource.retry} />
      ) : (
        resource.data && (
          <AttachmentEditor
            key={JSON.stringify(resource.data)}
            value={resource.data}
            done={resource.retry}
          />
        )
      )}
    </details>
  );
}

function AttachmentEditor({ value, done }: { value: MediaState; done: () => void }) {
  const [form, setForm] = useState({
    documents: value.documents,
    photos: value.photos,
    audio: value.audio,
    ocr_language: value.ocr_language,
    audio_language: value.audio_language,
  });
  const [model, setModel] = useState('');
  const [clear, setClear] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const toast = useToast();
  const options = [
    {
      id: 'documents' as const,
      title: 'Documents',
      note: 'PDF, UTF-8 text and Markdown · 8 MiB',
      icon: FileText,
      ready: value.ready.documents,
    },
    {
      id: 'photos' as const,
      title: 'Photo text',
      note: 'Local Tesseract OCR · JPEG / PNG',
      icon: Image,
      ready: value.dependencies.tesseract,
    },
    {
      id: 'audio' as const,
      title: 'Voice & audio',
      note: 'Local whisper.cpp · up to 2 minutes',
      icon: Mic,
      ready: value.dependencies.ffmpeg && value.dependencies.whisper,
    },
  ];
  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setError('');
        try {
          await api('/settings/messaging/telegram/attachments', {
            method: 'PUT',
            body: JSON.stringify({
              ...form,
              ...(model.trim() ? { whisper_model: model.trim() } : {}),
              clear_model: clear,
            }),
          });
          toast('Telegram attachment preferences saved.');
          done();
          refresh();
        } catch (reason) {
          setError(reason instanceof Error ? reason.message : 'Could not save preferences.');
        } finally {
          setBusy(false);
        }
      }}
    >
      <p className="footnote">{value.note}</p>
      <div className="telegram-attachment-options">
        {options.map(({ id, title, note, icon: Icon, ready }) => (
          <label className={form[id] ? 'selected' : ''} key={id}>
            <input
              type="checkbox"
              checked={form[id]}
              disabled={busy || (!ready && !form[id])}
              onChange={(event) => setForm({ ...form, [id]: event.target.checked })}
            />
            <Icon size={19} />
            <span>
              <strong>{title}</strong>
              <small>{note}</small>
            </span>
            {ready ? (
              form[id] ? (
                <Check size={14} />
              ) : (
                <Badge>Off</Badge>
              )
            ) : (
              <Badge>Setup needed</Badge>
            )}
          </label>
        ))}
      </div>
      <details className="telegram-attachment-processors">
        <summary>Local processor setup & languages</summary>
        <p className="footnote">
          Programs must be on the Python backend’s PATH. Installed files are detected locally;
          recognition accuracy and installed language packs are checked when processing. No cloud
          transcription is used.
        </p>
        <div className="telegram-processor-status">
          {(['tesseract', 'ffmpeg', 'whisper', 'model'] as const).map((key) => (
            <span key={key}>
              <i className={value.dependencies[key] ? 'present' : ''} />
              {key === 'whisper' ? 'whisper-cli' : key === 'model' ? 'Whisper model' : key} ·{' '}
              {value.dependencies[key] ? 'Found' : 'Missing'}
            </span>
          ))}
        </div>
        <div className="messaging-fields">
          <label>
            OCR languages
            <input
              value={form.ocr_language}
              onChange={(event) => setForm({ ...form, ocr_language: event.target.value })}
              placeholder="eng or eng+ell"
            />
            <small>Tesseract language packs, e.g. eng or eng+ell.</small>
          </label>
          <label>
            Audio language
            <input
              value={form.audio_language}
              onChange={(event) => setForm({ ...form, audio_language: event.target.value })}
              placeholder="auto"
            />
            <small>auto or a Whisper language code, e.g. en.</small>
          </label>
          <label className="telegram-model-path">
            Whisper model on the backend
            <input
              value={model}
              onChange={(event) => {
                setModel(event.target.value);
                setClear(false);
              }}
              placeholder={
                value.model_name ? `Saved: ${value.model_name}` : 'Absolute path to ggml-base.bin'
              }
              autoComplete="off"
            />
            <small>
              Select an existing whisper.cpp .bin model.{' '}
              {value.has_model
                ? 'Leave blank to keep the saved model.'
                : 'Install the model separately using the official instructions.'}
            </small>
          </label>
        </div>
        {value.model_name && (
          <label className="telegram-model-clear">
            <input
              type="checkbox"
              checked={clear}
              onChange={(event) => {
                setClear(event.target.checked);
                if (event.target.checked) setForm({ ...form, audio: false });
              }}
            />{' '}
            Forget the saved model path
          </label>
        )}
        <div className="telegram-processor-links">
          <a
            className="text-link"
            href="https://tesseract-ocr.github.io/tessdoc/Installation.html"
            target="_blank"
            rel="noreferrer"
          >
            Tesseract setup <ArrowUpRight size={12} />
          </a>
          <a
            className="text-link"
            href="https://ffmpeg.org/download.html"
            target="_blank"
            rel="noreferrer"
          >
            FFmpeg setup <ArrowUpRight size={12} />
          </a>
          <a
            className="text-link"
            href="https://github.com/ggml-org/whisper.cpp#quick-start"
            target="_blank"
            rel="noreferrer"
          >
            whisper.cpp & models <ArrowUpRight size={12} />
          </a>
        </div>
      </details>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <button className="button secondary" disabled={busy} type="submit">
        {busy && <LoaderCircle size={14} className="spin" />} Save attachment preferences
      </button>
    </form>
  );
}
