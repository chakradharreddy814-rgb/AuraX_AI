import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import Loading from '../components/Loading';
import ErrorBanner from '../components/ErrorBanner';
import { Button, Textarea } from '../components/Field';
import CameraConsent from '../components/CameraConsent';
import CameraPreview from '../components/CameraPreview';
import ViolationBanner from '../components/ViolationBanner';
import { useProctoring } from '../hooks/useProctoring';

// ─── Phases ─────────────────────────────────────────────────────────────────
// 'loading'    - fetching questions from API
// 'consent'    - showing camera consent screen
// 'declined'   - candidate declined camera access
// 'cam-init'   - requesting camera permission
// 'cam-error'  - camera permission denied or failed
// 'lobby'      - welcome/mode-select screen (camera already granted)
// 'interview'  - active interview with proctoring
// 'terminated' - interview ended early due to violations
// 'completed'  - interview successfully completed
// ────────────────────────────────────────────────────────────────────────────

export default function Interview() {
  const { candidateId } = useParams();
  
  const [phase, setPhase] = useState('loading');
  const [data, setData] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [cameraStream, setCameraStream] = useState(null);

  // Interview state
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState({});
  const [currentAnswer, setCurrentAnswer] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [interviewType, setInterviewType] = useState('speech'); // 'speech' or 'code' (written)

  // Violation tracking
  const [activeViolation, setActiveViolation] = useState(null);
  const [terminationViolations, setTerminationViolations] = useState([]);

  // Shared video ref for proctoring hook + preview
  const videoRef = useRef(null);
  const recognitionRef = useRef(null);

  // ─── Load interview details ──────────────────────────────────────────────
  useEffect(() => {
    api.getPublicInterview(candidateId)
      .then((res) => {
        setData(res);
        const groups = res.interview_questions || {};
        const qList = [
          ...(groups.technical_questions || []),
          ...(groups.behavioral_questions || []),
          ...(groups.gap_focused_questions || [])
        ];
        
        if (qList.length === 0) {
          qList.push(
            "Tell me about a challenging project you worked on recently.",
            "How do you handle disagreements within a engineering team?",
            "What are your core technical strengths and favorite tech stack?",
            "How do you keep your skills up to date with changing technologies?"
          );
        }
        setQuestions(qList);
        setPhase('consent'); // move to consent after load
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Invalid or expired interview link.');
        setPhase('error');
      });
  }, [candidateId]);

  // ─── Setup Speech Recognition ─────────────────────────────────────────────
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
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

      rec.onerror = (err) => {
        console.error('Speech recognition error:', err);
        setIsRecording(false);
      };

      rec.onend = () => {
        setIsRecording(false);
      };

      recognitionRef.current = rec;
    }
  }, []);

  // ─── Speak current question aloud ─────────────────────────────────────────
  const speakQuestion = (text) => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel(); // Stop any currently speaking voice
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.95; // Slightly slower for clarity
      window.speechSynthesis.speak(utterance);
    }
  };

  // Trigger speech synthesis when moving to next question
  useEffect(() => {
    if (phase === 'interview' && !submitting && questions[currentIdx]) {
      speakQuestion(questions[currentIdx]);
      setCurrentAnswer(answers[currentIdx] || '');
    }
  }, [phase, currentIdx, questions, submitting]);

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
      setPhase('lobby');
    } catch (err) {
      console.error('[Interview] Camera error:', err);
      setPhase('cam-error');
    }
  }, []);

  // ─── Stop camera ─────────────────────────────────────────────────────────
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
    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch {}
    }
    window.speechSynthesis?.cancel();
    stopCamera();
  }, [stopCamera]);

  useProctoring({
    videoRef,
    enabled: proctoringEnabled,
    onViolation: handleViolation,
    onTerminate: handleTerminate,
  });

  // ─── Submit handler ───────────────────────────────────────────────────────
  const handleSubmit = async (finalAnswers, proctoring = null) => {
    setSubmitting(true);
    setError('');
    stopCamera();

    const payload = questions.map((q, idx) => ({
      question: q,
      answer: finalAnswers[idx] || ''
    }));

    try {
      await api.submitInterview(candidateId, {
        answers: payload,
        answer_type: interviewType === 'speech' ? 'speech' : 'code',
        ...(proctoring ? { proctoring } : {})
      });
      setPhase('completed');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to submit interview answers. Please try again.');
      setSubmitting(false);
    }
  };

  const handleTerminatedSubmit = () => {
    const captured = { ...answers };
    if (currentAnswer.trim()) {
      captured[currentIdx] = currentAnswer;
    }
    handleSubmit(captured, {
      terminated_early: true,
      violations: terminationViolations.map((v) => ({
        type: v.type,
        description: v.description,
        timestamp: v.timestamp
      }))
    });
  };

  const handleStart = (type) => {
    setInterviewType(type);
    setPhase('interview');
  };

  const handleToggleRecord = () => {
    if (!recognitionRef.current) {
      alert('Speech recognition is not supported in this browser. Please type your response.');
      return;
    }

    if (isRecording) {
      recognitionRef.current.stop();
      setIsRecording(false);
    } else {
      try {
        recognitionRef.current.start();
        setIsRecording(true);
      } catch (err) {
        console.error(err);
      }
    }
  };

  const handleNext = () => {
    const newAnswers = { ...answers, [currentIdx]: currentAnswer };
    setAnswers(newAnswers);

    if (isRecording && recognitionRef.current) {
      recognitionRef.current.stop();
    }

    if (currentIdx < questions.length - 1) {
      setCurrentIdx((prev) => prev + 1);
    } else {
      handleSubmit(newAnswers);
    }
  };

  // ─── Render ───────────────────────────────────────────────────────────────

  if (phase === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-paper">
        <Loading label="Entering interview lobby…" />
      </div>
    );
  }

  if (phase === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-paper px-4">
        <div className="w-full max-w-md bg-surface border border-border-soft p-8 rounded-lg shadow-sm">
          <h1 className="font-display font-bold text-xl text-ink mb-4">Interview Portal</h1>
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
        <p className="text-xs text-slate">Please allow camera access when prompted.</p>
      </div>
    );
  }

  if (phase === 'cam-error') {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-paper px-4 gap-6">
        <div className="w-16 h-16 rounded-full flex items-center justify-center" style={{ backgroundColor: 'var(--color-band-weak-bg, #fff0f0)' }}>
          <svg className="w-8 h-8" style={{ color: 'var(--color-band-weak, #e74c3c)' }} fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M12 18.75H4.5A2.25 2.25 0 012.25 16.5V9M3 3l18 18" />
          </svg>
        </div>
        <div className="text-center max-w-sm">
          <h1 className="font-display font-bold text-xl text-ink mb-2">Camera Access Failed</h1>
          <p className="text-slate text-sm mb-4">
            We could not access your camera. Please check browser permissions and try again.
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

  if (phase === 'completed') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-paper px-4">
        <div className="w-full max-w-xl bg-surface border border-border-soft p-10 rounded-xl text-center shadow-lg">
          <div className="w-16 h-16 bg-band-exceptional-bg text-band-exceptional rounded-full flex items-center justify-center mx-auto mb-6">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
            </svg>
          </div>
          <h1 className="font-display font-bold text-2xl text-ink mb-2">Interview Completed!</h1>
          <p className="text-slate mb-6">
            Thank you, {data?.candidate_name}. Your answers have been recorded and sent to the recruiters for evaluation.
          </p>
          <p className="text-xs text-slate/70">You can safely close this browser window now.</p>
        </div>
      </div>
    );
  }

  if (phase === 'terminated') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-paper px-4">
        <div className="w-full max-w-xl bg-surface border border-border-soft p-10 rounded-xl text-center shadow-lg flex flex-col items-center gap-5">
          <div className="w-16 h-16 rounded-full flex items-center justify-center" style={{ backgroundColor: 'var(--color-band-weak-bg, #fff0f0)' }}>
            <svg className="w-8 h-8" style={{ color: 'var(--color-band-weak, #e74c3c)' }} fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
          </div>
          <div>
            <h1 className="font-display font-bold text-2xl text-ink mb-2">Interview Ended Early</h1>
            <p className="text-slate text-sm leading-relaxed">
              This interview was ended early due to repeated proctoring violations. Your answers up to this point will be submitted to the recruiters.
            </p>
          </div>
          {terminationViolations.length > 0 && (
            <div className="w-full bg-paper border border-border-soft rounded-lg p-4 text-left">
              <h3 className="text-xs font-semibold text-ink mb-3 font-display">Recorded violations:</h3>
              <ol className="flex flex-col gap-2">
                {terminationViolations.map((v, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="text-xs font-mono px-1.5 py-0.5 rounded shrink-0" style={{ backgroundColor: 'var(--color-band-weak-bg, #fff0f0)', color: 'var(--color-band-weak, #e74c3c)' }}>#{i + 1}</span>
                    <div>
                      <p className="text-xs font-medium text-ink">{v.description}</p>
                      <p className="text-[11px] text-slate font-mono">{new Date(v.timestamp).toLocaleTimeString()}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          )}
          <Button onClick={handleTerminatedSubmit} disabled={submitting}>
            {submitting ? 'Submitting...' : 'Submit Partial Responses'}
          </Button>
          {error && <ErrorBanner message={error} />}
        </div>
      </div>
    );
  }

  if (phase === 'lobby') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-paper px-4">
        <div className="w-full max-w-2xl bg-surface border border-border-soft p-8 rounded-xl shadow-md">
          <div className="flex items-center gap-2 mb-6">
            <span className="px-2.5 py-1 text-xs font-mono font-bold tracking-wide rounded" style={{ color: 'var(--color-rail)', backgroundColor: 'rgba(74, 85, 214, 0.1)' }}>
              AURAX AI LOBBY
            </span>
          </div>
          <h1 className="font-display font-extrabold text-3xl text-ink tracking-tight mb-2">
            Welcome, {data?.candidate_name}!
          </h1>
          <p className="text-slate text-sm mb-6">
            You have been invited to complete a self-guided interview for the position of{' '}
            <strong className="text-ink font-semibold">{data?.job_title}</strong> at{' '}
            <strong className="text-ink font-semibold">{data?.company_name}</strong>.
          </p>

          <div className="bg-paper p-5 rounded-lg border border-border-soft mb-8 flex flex-col gap-3">
            <h3 className="font-display text-sm font-semibold text-ink">Interview Format &amp; Instructions:</h3>
            <ul className="text-xs text-slate space-y-2 list-disc list-inside">
              <li>There are <strong className="text-ink font-medium">{questions.length} questions</strong> total.</li>
              <li>You can speak your answers (Voice mode) or type them (Written mode).</li>
              <li>In Voice mode, questions are read aloud. Tap the mic to record your answers.</li>
              <li>You will have the opportunity to review and edit transcribed answers before submitting.</li>
              <li>Camera proctoring is active. Please remain focused and in frame.</li>
            </ul>
          </div>

          <div className="flex flex-col sm:flex-row gap-4">
            <Button onClick={() => handleStart('speech')} className="flex-1 py-3 justify-center text-sm font-medium">
              Start Voice Interview (Recommended)
            </Button>
            <Button onClick={() => handleStart('code')} variant="secondary" className="flex-1 py-3 justify-center text-sm font-medium">
              Start Written Interview
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // ─── Active interview phase ──────────────────────────────────────────────
  const progressPercent = Math.round(((currentIdx + 1) / questions.length) * 100);

  return (
    <div className="min-h-screen flex flex-col justify-between bg-paper">
      {/* Violation toast */}
      <ViolationBanner violation={activeViolation} onDismiss={() => setActiveViolation(null)} />

      {/* Camera preview */}
      <CameraPreview videoRef={videoRef} position="bottom-right" />

      {/* Top Header */}
      <header className="bg-surface border-b border-border-soft px-6 py-4 flex items-center justify-between shadow-sm">
        <div>
          <span className="font-display font-bold text-lg text-ink">AuraX-AI</span>
          <span className="text-slate text-xs ml-3 border-l border-border-soft pl-3 font-mono">
            {data?.job_title}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {/* Proctoring pill */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-border-soft bg-paper text-xs text-slate font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block animate-pulse" />
            Proctored
          </div>
          <span className="text-xs font-mono text-slate">
            Question {currentIdx + 1} of {questions.length}
          </span>
          <div className="w-24 bg-border-soft h-2 rounded-full overflow-hidden">
            <div
              className="h-full transition-all duration-300"
              style={{ width: `${progressPercent}%`, backgroundColor: 'var(--color-rail)' }}
            />
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-3xl bg-surface border border-border-soft p-8 rounded-xl shadow-lg flex flex-col gap-6">
          
          <ErrorBanner message={error} />
          
          {/* Question Text */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono uppercase tracking-wider text-slate">
                Question {currentIdx + 1}
              </span>
              <button 
                onClick={() => speakQuestion(questions[currentIdx])}
                className="text-xs font-medium hover:opacity-80 transition-opacity flex items-center gap-1.5"
                style={{ color: 'var(--color-rail)' }}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z" />
                </svg>
                Listen Again
              </button>
            </div>
            <h2 className="font-display font-semibold text-xl md:text-2xl text-ink leading-snug">
              {questions[currentIdx]}
            </h2>
          </div>

          {/* Answer Input */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate font-medium">Your Response:</span>
              {interviewType === 'speech' && (
                <span className="text-xs text-slate font-mono flex items-center gap-1">
                  {isRecording ? (
                    <>
                      <span className="w-2 h-2 rounded-full bg-band-weak animate-ping" />
                      <span className="text-band-weak font-semibold">Recording... Speak now</span>
                    </>
                  ) : (
                    'Microphone ready'
                  )}
                </span>
              )}
            </div>

            <Textarea
              value={currentAnswer}
              onChange={(e) => setCurrentAnswer(e.target.value)}
              placeholder="Your answer will appear here. Feel free to refine it or type manually."
              rows={8}
              className="font-mono text-sm leading-relaxed"
            />
          </div>

          {/* Controls */}
          <div className="flex items-center justify-between gap-4 mt-2">
            {interviewType === 'speech' ? (
              <button
                type="button"
                onClick={handleToggleRecord}
                className={`w-14 h-14 rounded-full flex items-center justify-center border shadow-sm transition-all focus:outline-none ${
                  isRecording 
                    ? 'bg-band-weak-bg border-band-weak text-band-weak animate-[pulse-ring_1.5s_infinite]' 
                    : 'bg-paper hover:bg-border-soft border-border-soft text-slate hover:text-ink'
                }`}
                title={isRecording ? 'Stop Recording' : 'Start Recording'}
              >
                {isRecording ? (
                  <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                    <rect x="6" y="6" width="12" height="12" rx="2" />
                  </svg>
                ) : (
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
                  </svg>
                )}
              </button>
            ) : (
              <div /> // Spacer
            )}

            <Button
              onClick={handleNext}
              disabled={submitting || !currentAnswer.trim()}
              className="px-8 py-3"
            >
              {submitting 
                ? 'Submitting...' 
                : currentIdx < questions.length - 1 
                  ? 'Next Question' 
                  : 'Submit Interview'}
            </Button>
          </div>

        </div>
      </main>

      {/* Footer Info */}
      <footer className="py-4 text-center text-xs text-slate border-t border-border-soft bg-surface font-mono">
        AuraX-AI Safe &amp; Secure Recruitment System
      </footer>
    </div>
  );
}
