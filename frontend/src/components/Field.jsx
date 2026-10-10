export function Label({ children, htmlFor }) {
  return (
    <label htmlFor={htmlFor} className="block text-xs font-medium text-slate mb-1.5">
      {children}
    </label>
  );
}

export function Input(props) {
  return (
    <input
      {...props}
      className={`w-full rounded-md border border-border-soft bg-white px-3 py-2 text-sm text-ink placeholder:text-slate/50 outline-none focus:border-rail transition-colors ${props.className || ''}`}
      style={{ '--tw-ring-color': 'var(--color-rail)' }}
    />
  );
}

export function Textarea(props) {
  return (
    <textarea
      {...props}
      className={`w-full rounded-md border border-border-soft bg-white px-3 py-2 text-sm text-ink placeholder:text-slate/50 outline-none focus:border-rail transition-colors resize-y ${props.className || ''}`}
    />
  );
}

export function Select(props) {
  return (
    <select
      {...props}
      className={`rounded-md border border-border-soft bg-white px-3 py-2 text-sm text-ink outline-none focus:border-rail transition-colors ${props.className || ''}`}
    >
      {props.children}
    </select>
  );
}

export function Button({ children, variant = 'primary', className = '', ...props }) {
  const base = 'inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
  const variants = {
    primary: 'text-white',
    secondary: 'bg-white border border-border-soft text-ink hover:bg-paper',
    ghost: 'text-slate hover:text-ink',
  };
  const style = variant === 'primary' ? { backgroundColor: 'var(--color-rail)' } : undefined;
  return (
    <button {...props} className={`${base} ${variants[variant]} ${className}`} style={style}>
      {children}
    </button>
  );
}
