function getBand(score) {
  if (score >= 90) return { label: 'Exceptional', fg: 'var(--color-band-exceptional)', bg: 'var(--color-band-exceptional-bg)' };
  if (score >= 70) return { label: 'Strong', fg: 'var(--color-band-strong)', bg: 'var(--color-band-strong-bg)' };
  if (score >= 50) return { label: 'Partial', fg: 'var(--color-band-partial)', bg: 'var(--color-band-partial-bg)' };
  return { label: 'Weak', fg: 'var(--color-band-weak)', bg: 'var(--color-band-weak-bg)' };
}

export default function ScoreBadge({ score, size = 'md', showLabel = true }) {
  if (score === undefined || score === null) {
    return <span className="text-slate text-sm font-mono">—</span>;
  }
  const band = getBand(score);
  const sizeClasses = size === 'lg' ? 'text-lg px-3 py-1.5' : 'text-sm px-2.5 py-1';

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md font-mono font-semibold ${sizeClasses}`}
      style={{ color: band.fg, backgroundColor: band.bg }}
    >
      {Math.round(score)}
      {showLabel && <span className="font-body font-medium opacity-80">{band.label}</span>}
    </span>
  );
}

export { getBand };
