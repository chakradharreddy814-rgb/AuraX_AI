export default function Loading({ label = 'Loading…' }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-slate">
      <div className="relative w-8 h-8">
        <div
          className="absolute inset-0 rounded-full border-2 animate-spin"
          style={{
            borderColor: 'var(--color-border-soft)',
            borderTopColor: 'var(--color-rail)',
          }}
        />
      </div>
      <p className="text-sm font-medium">{label}</p>
    </div>
  );
}
