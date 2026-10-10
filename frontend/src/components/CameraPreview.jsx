/**
 * CameraPreview — small corner camera feed shown during the interview.
 * Provides visual proof to the candidate that the camera is active.
 */

export default function CameraPreview({ videoRef, position = 'bottom-right' }) {
  const positionStyles = {
    'bottom-right': { bottom: '1.25rem', right: '1.25rem' },
    'top-right':    { top: '1.25rem', right: '1.25rem' },
    'bottom-left':  { bottom: '1.25rem', left: '1.25rem' },
  };

  return (
    <div
      style={{
        position: 'fixed',
        ...positionStyles[position],
        width: '128px',
        height: '96px',
        borderRadius: '10px',
        overflow: 'hidden',
        border: '2px solid rgba(255,255,255,0.3)',
        boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
        zIndex: 100,
        backgroundColor: '#111',
      }}
    >
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transform: 'scaleX(-1)', // mirror so it looks natural
          display: 'block',
        }}
      />
      {/* Live indicator dot */}
      <div
        style={{
          position: 'absolute',
          top: '6px',
          left: '6px',
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          backgroundColor: 'rgba(0,0,0,0.5)',
          borderRadius: '9999px',
          padding: '2px 6px',
        }}
      >
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            backgroundColor: '#ef4444',
            display: 'inline-block',
            animation: 'pulse 1.5s ease-in-out infinite',
          }}
        />
        <span style={{ fontSize: '9px', color: 'white', fontWeight: 700, letterSpacing: '0.05em' }}>
          LIVE
        </span>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </div>
  );
}
