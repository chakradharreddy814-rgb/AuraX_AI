/**
 * ViolationBanner — animated toast shown on each proctoring violation.
 * Auto-dismisses after 6 seconds. Shows warning number and reason.
 */

import { useEffect, useState } from 'react';

export default function ViolationBanner({ violation, onDismiss }) {
  const [visible, setVisible] = useState(false);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    if (!violation) return;

    setVisible(true);
    setExiting(false);

    const dismissTimer = setTimeout(() => {
      setExiting(true);
      setTimeout(() => {
        setVisible(false);
        onDismiss?.();
      }, 300);
    }, 6000);

    return () => clearTimeout(dismissTimer);
  }, [violation, onDismiss]);

  if (!visible || !violation) return null;

  const isTerminating = violation.warningNumber >= 3;

  return (
    <div
      style={{
        position: 'fixed',
        top: '1.25rem',
        left: '50%',
        transform: `translateX(-50%) translateY(${exiting ? '-120%' : '0'})`,
        transition: 'transform 0.3s ease, opacity 0.3s ease',
        opacity: exiting ? 0 : 1,
        zIndex: 9999,
        maxWidth: '480px',
        width: 'calc(100% - 2rem)',
      }}
    >
      <div
        style={{
          backgroundColor: isTerminating ? 'var(--color-band-weak-bg, #fff0f0)' : '#fffbeb',
          border: `1.5px solid ${isTerminating ? 'var(--color-band-weak, #e74c3c)' : '#f59e0b'}`,
          borderRadius: '10px',
          padding: '14px 16px',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '12px',
          boxShadow: '0 4px 24px rgba(0,0,0,0.12)',
        }}
      >
        {/* Icon */}
        <div
          style={{
            flexShrink: 0,
            width: '32px',
            height: '32px',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: isTerminating ? 'var(--color-band-weak, #e74c3c)' : '#f59e0b',
          }}
        >
          <svg
            width="16"
            height="16"
            fill="none"
            stroke="white"
            strokeWidth="2.5"
            viewBox="0 0 24 24"
          >
            {isTerminating ? (
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9.303 3.376c.866 1.5-.217 3.374-1.948 3.374H4.645c-1.73 0-2.813-1.874-1.948-3.374L10.051 3.378c.866-1.5 3.032-1.5 3.898 0L21.303 16.126z" />
            )}
          </svg>
        </div>

        {/* Text content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <p
            style={{
              fontSize: '13px',
              fontWeight: 700,
              color: isTerminating ? 'var(--color-band-weak, #c0392b)' : '#92400e',
              marginBottom: '2px',
            }}
          >
            {isTerminating
              ? '🚫 Interview Terminated'
              : `⚠ Violation detected — Warning ${violation.warningNumber} of 2`}
          </p>
          <p
            style={{
              fontSize: '12px',
              color: isTerminating ? 'var(--color-band-weak, #c0392b)' : '#b45309',
              lineHeight: 1.4,
            }}
          >
            {violation.description}
            {!isTerminating && (
              <span style={{ opacity: 0.75 }}>
                {' '}— {2 - violation.warningNumber} warning{2 - violation.warningNumber !== 1 ? 's' : ''} remaining before the interview is automatically ended.
              </span>
            )}
          </p>
        </div>

        {/* Dismiss button */}
        <button
          onClick={() => {
            setExiting(true);
            setTimeout(() => { setVisible(false); onDismiss?.(); }, 300);
          }}
          style={{
            flexShrink: 0,
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '2px',
            color: isTerminating ? 'var(--color-band-weak, #c0392b)' : '#92400e',
            opacity: 0.6,
          }}
          aria-label="Dismiss"
        >
          <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  );
}
