import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import Loading from '../components/Loading';
import ErrorBanner from '../components/ErrorBanner';
import { Button } from '../components/Field';
import CameraConsent from '../components/CameraConsent';
import CameraPreview from '../components/CameraPreview';
import ViolationBanner from '../components/ViolationBanner';
import { useProctoring } from '../hooks/useProctoring';

// ─── Phases ────────────────────────────────────────────────────────────────
// 'loading'   - fetching questions from API
// 'consent'   - showing camera consent screen
// 'declined'  - candidate declined camera access
// 'cam-init'  - requesting camera permission
// 'cam-error' - camera permission denied or failed
// 'interview' - active interview with proctoring
// 'terminated'- interview ended early due to violations
// 'submitted' - interview successfully submitted
// ───────────────────────────────────────────────────────────────────────────

export default function PublicInterview() {
  const { candidateId } = useParams();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [phase, setPhase] = useState('loading');
  const [questions, setQuestions] = useState(null);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [cameraStream, setCameraStream] = useState(null);

  // Violation tracking
  const [activeViolation, setActiveViolation] = useState(null);
  const [terminationViolations, setTerminationViolations] = useState([]);

  // Shared video ref for proctoring hook + preview
  const videoRef = useRef(null);

  // ─── Load questions ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!token) {
      setError('Invalid interview link — missing token.');
      setPhase('error');
      return;
    }

    let cancelled = false;
    api.getPublicInterviewQuestions(candidateId, token)
      .then((data) => {
        if (!cancelled) {
          setQuestions(data);
          setPhase('consent'); // move to consent after load
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Could not load interview.');
          setPhase('error');
        }
      });

    return () => { cancelled = true; };
  }, [candidateId, token]);

  // ─── Attach stream to video element ─────────────────────────────────────
  useEffect(() => {
    if (cameraStream && videoRef.current) {
      videoRef.current.srcObject = cameraStream;
    }
  }, [cameraStream, phase]);

  // ─── Camera access ───────────────────────────────────────────────────────
  const requestCamera = useCallback(async () => {
    setPhase('cam-init');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      setCameraStream(stream);
      setPhase('interview');
    } catch (err) {
      console.error('[PublicInterview] Camera error:', err);
      setPhase('cam-error');
    }
  }, []);

  // ─── Stop camera on unmount or termination ───────────────────────────────
  const stopCamera = useCallback(() => {
    if (cameraStream) {
      cameraStream.getTracks().forEach((t) => t.stop());
      setCameraStream(null);
    }
  }, [cameraStream]);

  useEffect(() => {
    return () => stopCamera();
  }, [stopCamera]);

  // ─── Proctoring hook ─────────────────────────────────────────────────────
  const proctoringEnabled = phase === 'interview';

  const handleViolation = useCallback((violation) => {
    setActiveViolation(violation);
  }, []);

  const handleTerminate = useCallback((allViolations) => {
    setTerminationViolations(allViolations);
    setPhase('terminated');
    stopCamera();
    // Auto-submit with partial answers is handled below in TerminatedScreen
  }, [stopCamera]);

  useProctoring({
    videoRef,
    enabled: proctoringEnabled,
    onViolation: handleViolation,
    onTerminate: handleTerminate,
  });

  // ─── Submit handler ───────────────────────────────────────────────────────
  const handleSubmit = useCallback(async (answers, proctoring = null) => {
    if (submitting) return;
    setSubmitting(true);
    stopCamera();

    try {
      const body = { answers };
      if (proctoring) body.proctoring = proctoring;

      await api.submitPublicInterview(candidateId, token, body);
      setPhase('submitted');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to submit interview.');
      setSubmitting(false);
    }
  }, [submitting, candidateId, token, stopCamera]);

  // ─── Render ───────────────────────────────────────────────────────────────

  if (phase === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-paper">
        <Loading label="Loading interview..." />
      </div>
    );
  }

  if (phase === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-paper px-4">
        <div className="max-w-md w-full">
          <ErrorBanner message={error || 'Invalid or expired interview link.'} />
        </div>
      </div>
    );
  }

  if (phase === 'consent') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-paper px-4">
        <div className="w-full max-w-lg bg-surface border border-border-soft rounded-xl shadow-md">
          <CameraConsent
            onAgree={requestCamera}
            onDecline={() => setPhase('declined')}
          />
        </div>
      </div>
    );
  }

  if (phase === 'declined') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-paper px-4 gap-6">
        <div className="w-16 h-16 rounded-full flex items-center justify-center bg-paper border border-border-soft">
          <svg className="w-8 h-8 text-slate" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M12 18.75H4.5A2.25 2.25 0 012.25 16.5V9M3 3l18 18" />
          </svg>
        </div>
        <div className="text-center max-w-sm">
          <h1 className="font-display font-bold text-xl text-ink mb-2">Camera Access Declined</h1>
          <p className="text-slate text-sm">
            Camera access is required to proceed with this interview. If you change your mind,
            please refresh the page and click &ldquo;I agree&rdquo; on the consent screen.
          </p>
        </div>
      </div>
    );
  }

  if (phase === 'cam-init') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-paper gap-4">
        <Loading label="Starting camera..." />
        <p className="text-xs text-slate">Please allow camera access when your browser asks.</p>
      </div>
    );
  }

  if (phase === 'cam-error') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-paper px-4 gap-6">
        <div
          className="w-16 h-16 rounded-full flex items-center justify-center"
          style={{ backgroundColor: 'var(--color-band-weak-bg, #fff0f0)' }}
        >
          <svg className="w-8 h-8" style={{ color: 'var(--color-band-weak, #e74c3c)' }} fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M12 18.75H4.5A2.25 2.25 0 012.25 16.5V9M3 3l18 18" />
          </svg>
        </div>
        <div className="text-center max-w-sm">
          <h1 className="font-display font-bold text-xl text-ink mb-2">Camera Access Failed</h1>
          <p className="text-slate text-sm mb-4">
            We could not access your camera. Please check that your browser has permission to use the camera, then try again.
          </p>
          <button
            onClick={requestCamera}
            className="px-5 py-2.5 text-sm font-medium rounded-lg border border-border-soft hover:bg-paper transition-colors"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (phase === 'submitted') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-paper px-4">
        <div className="max-w-md text-center">
          <div className="mb-6">
            <div
              className="w-20 h-20 mx-auto rounded-full flex items-center justify-center mb-4"
              style={{ backgroundColor: 'var(--color-signal)' }}
            >
              <svg className="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="font-display text-2xl font-semibold text-ink">Thank you!</h1>
            <p className="text-slate mt-2">
              Your interview has been submitted successfully. We&apos;ll review your responses and be in touch soon.
            </p>
          </div>
          <div className="text-sm text-slate bg-surface border border-border-soft rounded-lg p-4">
            <p>The hiring team will contact you at the email you provided with next steps.</p>
          </div>
        </div>
      </div>
    );
  }

  // ─── Active interview (with proctoring) ───────────────────────────────────
  return (
    <div className="min-h-screen bg-paper">
      {/* Violation toast */}
      <ViolationBanner
        violation={activeViolation}
        onDismiss={() => setActiveViolation(null)}
      />

      {/* Live camera preview */}
      {phase === 'interview' && <CameraPreview videoRef={videoRef} position="bottom-right" />}

      {/* Minimal header */}
      <header className="px-6 py-6 border-b border-border-soft bg-white">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="font-display text-2xl font-semibold text-ink">
              Interview: {questions?.candidate_name}
            </h1>
            <p className="text-sm text-slate mt-1">{questions?.questions?.length} questions</p>
          </div>
          {/* Proctoring indicator */}
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-border-soft bg-paper text-xs text-slate font-mono">
            <span className="w-2 h-2 rounded-full bg-green-500 inline-block" style={{ animation: 'pulse 2s ease-in-out infinite' }} />
            Proctored
          </div>
        </div>
      </header>

      {/* Interview content */}
      <main className="max-w-3xl mx-auto px-6 py-8 pb-36">
        {phase === 'terminated' ? (
          <TerminatedScreen
            violations={terminationViolations}
            onSubmitPartial={(answers) =>
              handleSubmit(answers, {
                terminated_early: true,
                violations: terminationViolations.map((v) => ({
                  type: v.type,
                  description: v.description,
                  timestamp: v.timestamp,
                })),
              })
            }
            submitting={submitting}
          />
        ) : (
          <InterviewFlow
            questions={questions?.questions || []}
            candidateName={questions?.candidate_name}
            onComplete={(answers) => handleSubmit(answers, null)}
            submitting={submitting}
          />
        )}
      </main>

      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }`}</style>
    </div>
  );
}

// ─── Terminated Screen ────────────────────────────────────────────────────────
function TerminatedScreen({ violations, onSubmitPartial, submitting }) {
  const [submitted, setSubmitted] = useState(false);

  const handleSubmitPartial = async () => {
    // Submit empty answers (whatever was captured) — the parent handles the API call
    await onSubmitPartial([]);
    setSubmitted(true);
  };

  return (
    <div className="flex flex-col items-center gap-6 py-12 text-center">
      <div
        className="w-20 h-20 rounded-full flex items-center justify-center"
        style={{ backgroundColor: 'var(--color-band-weak-bg, #fff0f0)' }}
      >
        <svg className="w-10 h-10" style={{ color: 'var(--color-band-weak, #e74c3c)' }} fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
        </svg>
      </div>

      <div className="max-w-md">
        <h2 className="font-display font-bold text-2xl text-ink mb-2">Interview Ended Early</h2>
        <p className="text-slate text-sm leading-relaxed">
          This interview was ended due to repeated proctoring violations. Your responses up to this point
          have been recorded and will be reviewed by the hiring team along with the proctoring report.
        </p>
      </div>

      {violations.length > 0 && (
        <div className="w-full max-w-md bg-surface border border-border-soft rounded-lg p-4 text-left">
          <h3 className="text-xs font-semibold text-ink mb-3">Recorded violations:</h3>
          <ol className="flex flex-col gap-2">
            {violations.map((v, i) => (
              <li key={i} className="flex items-start gap-2">
                <span
                  className="text-xs font-mono px-1.5 py-0.5 rounded shrink-0 mt-0.5"
                  style={{ backgroundColor: 'var(--color-band-weak-bg, #fff0f0)', color: 'var(--color-band-weak, #e74c3c)' }}
                >
                  #{i + 1}
                </span>
                <div>
                  <p className="text-xs font-medium text-ink">{v.description}</p>
                  <p className="text-[11px] text-slate font-mono">{new Date(v.timestamp).toLocaleTimeString()}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}

      {!submitted && (
        <button
          onClick={handleSubmitPartial}
          disabled={submitting}
          className="px-6 py-2.5 rounded-lg text-sm font-medium border border-border-soft bg-surface hover:bg-paper transition-colors disabled:opacity-50"
        >
          {submitting ? 'Submitting...' : 'Acknowledge & Close'}
        </button>
      )}
      {submitted && (
        <p className="text-sm text-slate">Your session has been submitted. You may close this window.</p>
      )}
    </div>
  );
}

// ─── Interview Flow ───────────────────────────────────────────────────────────
function InterviewFlow({ questions, candidateName, onComplete, submitting }) {
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState({});
  const [currentAnswer, setCurrentAnswer] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const recognitionRef = useRef(null);

  const currentQuestion = questions[currentIdx];

  // Setup speech recognition
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;
    const rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = 'en-US';
    rec.onresult = (e) => {
      let transcript = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        transcript += e.results[i][0].transcript;
      }
      setCurrentAnswer((prev) => prev.trim() ? prev + ' ' + transcript : transcript);
    };
    rec.onend = () => setIsRecording(false);
    rec.onerror = () => setIsRecording(false);
    recognitionRef.current = rec;
  }, []);

  const handleRecord = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('Speech recognition not supported in this browser');
      return;
    }
    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
    } else {
      try {
        recognitionRef.current?.start();
        setIsRecording(true);
      } catch (e) { /* already running */ }
    }
  };

  const handleNext = () => {
    if (!currentAnswer.trim()) {
      alert('Please provide an answer before moving to the next question');
      return;
    }
    const newAnswers = { ...answers, [currentIdx]: { question: currentQuestion, answer: currentAnswer.trim() } };
    setAnswers(newAnswers);
    if (currentIdx < questions.length - 1) {
      setCurrentIdx(currentIdx + 1);
      setCurrentAnswer('');
    }
  };

  const handleSubmit = async () => {
    if (!currentAnswer.trim()) {
      alert('Please provide an answer to the last question');
      return;
    }
    const finalAnswers = [
      ...Object.values(answers),
      { question: currentQuestion, answer: currentAnswer.trim() },
    ];
    await onComplete(finalAnswers);
  };

  const progress = Math.round(((currentIdx + 1) / questions.length) * 100);
  const isLastQuestion = currentIdx === questions.length - 1;

  return (
    <div className="space-y-6">
      {/* Progress */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-medium text-ink">Question {currentIdx + 1} of {questions.length}</p>
          <p className="text-sm text-slate">{progress}%</p>
        </div>
        <div className="w-full h-2 bg-border-soft rounded-full overflow-hidden">
          <div className="h-full transition-all duration-300" style={{ width: `${progress}%`, backgroundColor: 'var(--color-signal)' }} />
        </div>
      </div>

      {/* Question */}
      <div className="bg-white border border-border-soft rounded-lg p-6">
        <p className="text-lg font-medium text-ink mb-6">{currentQuestion}</p>
        <div className="space-y-4">
          <div className="border border-border-soft rounded-lg p-4 bg-paper min-h-24">
            {currentAnswer && <p className="text-sm text-ink">{currentAnswer}</p>}
            {!currentAnswer && !isRecording && <p className="text-sm text-slate italic">Your answer will appear here...</p>}
            {isRecording && (
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                <p className="text-sm text-slate">Recording...</p>
              </div>
            )}
          </div>
          <div className="flex flex-col gap-3">
            <Button variant={isRecording ? 'secondary' : 'primary'} onClick={handleRecord} className="w-full">
              {isRecording ? 'Stop recording' : 'Start recording'}
            </Button>
            {!isRecording && (
              <Button variant="secondary" onClick={() => setCurrentAnswer('')} disabled={!currentAnswer}>
                Clear answer
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Navigation */}
      <div className="flex gap-3 justify-between">
        <Button
          variant="secondary"
          onClick={() => {
            setCurrentIdx(Math.max(0, currentIdx - 1));
            setCurrentAnswer(answers[currentIdx - 1]?.answer || '');
          }}
          disabled={currentIdx === 0 || submitting}
        >
          ← Previous
        </Button>
        <Button onClick={isLastQuestion ? handleSubmit : handleNext} disabled={submitting || !currentAnswer.trim()}>
          {submitting ? 'Submitting...' : isLastQuestion ? 'Submit interview' : 'Next →'}
        </Button>
      </div>
    </div>
  );
}
