export default function EmptyState({ title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center text-center gap-4 py-24 px-6 rounded-lg border border-dashed border-border-soft bg-surface/40">
      {/* Icon */}
      <div className="w-16 h-16 rounded-full flex items-center justify-center" style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)' }}>
        <svg 
          className="w-8 h-8" 
          fill="none" 
          stroke="var(--color-signal)" 
          strokeWidth="2" 
          strokeLinecap="round" 
          strokeLinejoin="round"
          viewBox="0 0 24 24"
        >
          <rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect>
          <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path>
        </svg>
      </div>
      
      <div className="flex flex-col gap-2">
        <h3 className="font-display text-lg font-semibold text-ink">{title}</h3>
        {description && <p className="text-sm text-slate max-w-md leading-relaxed">{description}</p>}
      </div>
      
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
