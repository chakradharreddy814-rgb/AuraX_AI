export default function ErrorBanner({ message }) {
  if (!message) return null;
  return (
    <div
      className="rounded-md px-4 py-3 text-sm font-medium"
      style={{ color: 'var(--color-band-weak)', backgroundColor: 'var(--color-band-weak-bg)' }}
      role="alert"
    >
      {message}
    </div>
  );
}
