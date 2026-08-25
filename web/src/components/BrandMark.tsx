/**
 * The board glyph: a slate with a mark rising across it. Used on the login
 * screen, where there is no room name to identify the app yet, and cut into
 * the PWA icon. Inside the app the room name does this job instead.
 */
export function BrandMark({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 22 22"
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <rect
        x="2.2"
        y="3.6"
        width="17.6"
        height="13"
        rx="2.4"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <path
        d="M5.6 12.6l3.1-3.4 2.6 2.1 4.9-4.4"
        stroke="var(--color-good)"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M8 19.2h6"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}
