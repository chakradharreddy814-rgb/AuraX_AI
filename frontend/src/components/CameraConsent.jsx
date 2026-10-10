/**
 * CameraConsent — step shown BEFORE getUserMedia is called.
 * Candidate must explicitly agree before any camera access is requested.
 */

import { Button } from './Field';

export default function CameraConsent({ onAgree, onDecline }) {
  return (
    <div className="p-6 flex flex-col gap-6">
      {/* Header badge */}
      <div className="flex items-center gap-2">
        <span
          className="px-2.5 py-1 text-xs font-mono font-bold tracking-wide rounded"
          style={{ color: 'var(--color-rail)', backgroundColor: 'rgba(74, 85, 214, 0.1)' }}
        >
          PROCTORED INTERVIEW
        </span>
      </div>

      {/* Camera icon */}
      <div
        className="w-14 h-14 rounded-full flex items-center justify-center mx-auto"
        style={{ backgroundColor: 'rgba(74, 85, 214, 0.1)' }}
      >
        <svg
          className="w-7 h-7"
          style={{ color: 'var(--color-rail)' }}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25V7.5A2.25 2.25 0 0013.5 5.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z"
          />
        </svg>
      </div>

      {/* Title + explanation */}
      <div className="text-center">
        <h2 className="font-display font-bold text-xl text-ink mb-2">
          Camera Access Required
        </h2>
        <p className="text-slate text-sm leading-relaxed max-w-md mx-auto">
          This interview uses your camera to verify you remain present and focused
          during the session.
        </p>
      </div>

      {/* Privacy promise card */}
      <div className="bg-paper border border-border-soft rounded-lg p-4 flex flex-col gap-3">
        <h3 className="text-xs font-semibold text-ink flex items-center gap-1.5">
          <svg className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--color-band-exceptional)' }} fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
          </svg>
          Your privacy is protected
        </h3>
        <ul className="text-xs text-slate space-y-2 list-none">
          <li className="flex items-start gap-2">
            <span className="mt-0.5 shrink-0 w-1.5 h-1.5 rounded-full bg-slate/40 mt-1.5" />
            Your camera feed is <strong className="text-ink font-medium">not recorded or stored</strong> — only used for real-time monitoring during the interview.
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 shrink-0 w-1.5 h-1.5 rounded-full bg-slate/40 mt-1.5" />
            Detection runs entirely <strong className="text-ink font-medium">on your device</strong> — no video is ever sent to our servers.
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 shrink-0 w-1.5 h-1.5 rounded-full bg-slate/40 mt-1.5" />
            The system monitors: face presence, <strong className="text-ink font-medium">whether you are facing the screen</strong>, multiple people in frame, and electronic devices visible in frame.
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 shrink-0 w-1.5 h-1.5 rounded-full bg-slate/40 mt-1.5" />
            After <strong className="text-ink font-medium">3 violations</strong>, the interview will be automatically ended and your partial responses submitted.
          </li>
        </ul>
      </div>

      {/* CTA buttons */}
      <div className="flex flex-col gap-3">
        <Button
          id="proctoring-consent-agree"
          onClick={onAgree}
          className="w-full justify-center py-3"
        >
          I agree, start interview
        </Button>
        <button
          id="proctoring-consent-decline"
          onClick={onDecline}
          className="text-sm text-slate hover:text-ink transition-colors text-center py-2"
        >
          No, I don&apos;t agree — I cannot proceed without camera access
        </button>
      </div>
    </div>
  );
}
