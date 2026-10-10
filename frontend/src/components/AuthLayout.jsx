export default function AuthLayout({ title, subtitle, children }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-paper px-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center mb-8">
          <img src="/brand/aurax-mark.png" alt="AuraX-AI" className="h-14 w-auto mb-2" />
          <span className="font-display font-semibold text-ink text-xl tracking-tight">AuraX-AI</span>
          <span className="text-[11px] text-slate tracking-wide uppercase mt-0.5">AI-Powered Hiring Agent</span>
        </div>

        <div className="bg-surface rounded-lg border border-border-soft shadow-sm px-7 py-8">
          <h1 className="font-display text-xl font-semibold text-ink">{title}</h1>
          {subtitle && <p className="text-sm text-slate mt-1.5">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
      </div>
    </div>
  );
}
