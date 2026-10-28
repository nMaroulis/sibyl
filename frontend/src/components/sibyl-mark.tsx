/** A code-drawn brand mark shared by Sibyl's page and navigation entry. */
export function SibylMark({ small = false }: { small?: boolean }) {
  return (
    <span className={`sibyl-mark ${small ? 'small' : ''}`} aria-hidden="true">
      <svg viewBox="0 0 48 48" fill="none">
        <path
          d="M24 6C26 17 31 22 42 24C31 26 26 31 24 42C22 31 17 26 6 24C17 22 22 17 24 6Z"
          fill="currentColor"
        />
        <circle cx="38" cy="10" r="3" fill="currentColor" opacity=".65" />
      </svg>
    </span>
  );
}
