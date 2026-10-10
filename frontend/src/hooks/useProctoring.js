/**
 * useProctoring — camera-based interview proctoring hook
 *
 * Responsibilities:
 *  - Manages the camera MediaStream
 *  - Loads MediaPipe FaceLandmarker for face presence / multi-face / head-turn detection
 *  - Loads TF.js + COCO-SSD for phone/device detection
 *  - Tracks violations with a 10-second debounce per type
 *  - Exposes violation log, warning count, and terminated flag
 *  - Calls onTerminate(violations) when warningCount reaches 3
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import * as cocoSsd from '@tensorflow-models/coco-ssd';
import '@tensorflow/tfjs';

// MediaPipe is imported per their recommended pattern for Vite/ESM
import { FaceLandmarker, FilesetResolver } from '@mediapipe/tasks-vision';

// How long (ms) a face must be continuously absent to trigger a violation
const FACE_ABSENT_THRESHOLD_MS = 3000;

// How long (ms) the head must stay turned away to trigger a violation
const FACE_TURNED_THRESHOLD_MS = 3000;

// Head yaw (rotation left/right) beyond which the candidate is "looking away"
// radians — ~25° gives a comfortable margin over normal screen reading posture
const FACE_TURNED_YAW_RAD = 0.44;

// Minimum interval (ms) between registering the same violation type again
const VIOLATION_DEBOUNCE_MS = 10000;

// Phone detection interval (ms) — run every 2.5 seconds
const PHONE_DETECT_INTERVAL_MS = 2500;

// COCO-SSD classes we care about
const DEVICE_CLASSES = ['cell phone', 'laptop', 'tablet'];

export function useProctoring({ videoRef, enabled, onViolation, onTerminate }) {
  const [violations, setViolations] = useState([]);
  const [warningCount, setWarningCount] = useState(0);
  const [terminated, setTerminated] = useState(false);
  const [modelsReady, setModelsReady] = useState(false);

  // Internal refs — don't cause re-renders
  const faceLandmarkerRef = useRef(null);
  const cocoModelRef = useRef(null);
  const rafIdRef = useRef(null);
  const phoneIntervalRef = useRef(null);
  const faceAbsentSinceRef = useRef(null); // timestamp when face first went missing
  const faceTurnedSinceRef = useRef(null); // timestamp when head first turned away
  const lastViolationTimeRef = useRef({}); // { violationType: timestamp }
  const warningCountRef = useRef(0);       // shadow of warningCount for use inside callbacks
  const terminatedRef = useRef(false);
  const violationsRef = useRef([]);

  // ─── Load both ML models once ────────────────────────────────────────────────
  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;

    async function loadModels() {
      try {
        // 1. TF.js COCO-SSD
        const cocoModel = await cocoSsd.load({ base: 'lite_mobilenet_v2' });
        if (!cancelled) cocoModelRef.current = cocoModel;

        // 2. MediaPipe FaceLandmarker
        const filesetResolver = await FilesetResolver.forVisionTasks(
          'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@latest/wasm'
        );
        const landmarker = await FaceLandmarker.createFromOptions(filesetResolver, {
          baseOptions: {
            modelAssetPath:
              'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
            delegate: 'GPU',
          },
          runningMode: 'VIDEO',
          numFaces: 4, // detect up to 4 to catch multi-face
          outputFaceBlendshapes: false,
          // Matrix lets us compute head yaw (looking left/right = violation)
          outputFacialTransformationMatrixes: true,
        });
        if (!cancelled) {
          faceLandmarkerRef.current = landmarker;
          setModelsReady(true);
        }
      } catch (err) {
        console.warn('[useProctoring] Model load failed:', err);
        // Don't block the interview — proctoring degrades gracefully
        if (!cancelled) setModelsReady(true);
      }
    }

    loadModels();
    return () => { cancelled = true; };
  }, [enabled]);

  // ─── Violation registration ───────────────────────────────────────────────
  const registerViolation = useCallback((type, description) => {
    if (terminatedRef.current) return;

    const now = Date.now();
    const last = lastViolationTimeRef.current[type] || 0;

    // Debounce: don't re-fire the same type within 10 seconds
    if (now - last < VIOLATION_DEBOUNCE_MS) return;
    lastViolationTimeRef.current[type] = now;

    const newWarningCount = warningCountRef.current + 1;
    warningCountRef.current = newWarningCount;

    const violation = {
      type,
      description,
      timestamp: new Date().toISOString(),
      warningNumber: newWarningCount,
    };

    const newViolations = [...violationsRef.current, violation];
    violationsRef.current = newViolations;

    setViolations(newViolations);
    setWarningCount(newWarningCount);
    onViolation?.(violation, newWarningCount);

    if (newWarningCount >= 3) {
      terminatedRef.current = true;
      setTerminated(true);
      onTerminate?.(newViolations);
    }
  }, [onViolation, onTerminate]);

  // ─── Face detection loop (rAF) ────────────────────────────────────────────
  useEffect(() => {
    if (!enabled || !modelsReady) return;

    let lastTimestamp = -1;

    function detect() {
      if (terminatedRef.current) return;

      const video = videoRef.current;
      if (!video || video.readyState < 2 || !faceLandmarkerRef.current) {
        rafIdRef.current = requestAnimationFrame(detect);
        return;
      }

      const now = performance.now();
      // Throttle to ~8 fps for perf (face detection every ~125ms)
      if (now - lastTimestamp < 125) {
        rafIdRef.current = requestAnimationFrame(detect);
        return;
      }
      lastTimestamp = now;

      try {
        const result = faceLandmarkerRef.current.detectForVideo(video, now);
        const faceCount = result?.faceLandmarks?.length ?? 0;

        if (faceCount === 0) {
          // Start tracking absence time
          if (faceAbsentSinceRef.current === null) {
            faceAbsentSinceRef.current = Date.now();
          } else if (Date.now() - faceAbsentSinceRef.current >= FACE_ABSENT_THRESHOLD_MS) {
            registerViolation('face_absent', 'Face not visible — candidate may have stepped away');
          }
          faceTurnedSinceRef.current = null;
        } else {
          // Face is back — reset absence timer
          faceAbsentSinceRef.current = null;

          if (faceCount >= 2) {
            registerViolation('multiple_faces', 'Multiple faces detected in frame');
          }

          // ── Head-turn (looking away) detection ─────────────────────────
          // The facial transformation matrix is column-major 4x4; its
          // rotation part yields head yaw. |yaw| > ~25° ≈ candidate is
          // looking off-screen rather than at the interview.
          const matrix = result?.facialTransformationMatrixes?.[0]?.data;
          if (matrix && faceCount === 1) {
            const yaw = Math.abs(Math.atan2(matrix[8], matrix[10]));
            if (yaw > FACE_TURNED_YAW_RAD) {
              if (faceTurnedSinceRef.current === null) {
                faceTurnedSinceRef.current = Date.now();
              } else if (Date.now() - faceTurnedSinceRef.current >= FACE_TURNED_THRESHOLD_MS) {
                registerViolation(
                  'face_turned',
                  'Candidate looking away from the screen — face must stay visible and facing forward'
                );
                faceTurnedSinceRef.current = Date.now(); // debounce via threshold re-arm
              }
            } else {
              faceTurnedSinceRef.current = null;
            }
          } else {
            faceTurnedSinceRef.current = null;
          }
        }
      } catch (err) {
        // Silently ignore detection errors
      }

      rafIdRef.current = requestAnimationFrame(detect);
    }

    rafIdRef.current = requestAnimationFrame(detect);

    return () => {
      if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
    };
  }, [enabled, modelsReady, videoRef, registerViolation]);

  // ─── Phone / device detection interval ────────────────────────────────────
  useEffect(() => {
    if (!enabled || !modelsReady) return;

    phoneIntervalRef.current = setInterval(async () => {
      if (terminatedRef.current) return;
      const video = videoRef.current;
      if (!video || video.readyState < 2 || !cocoModelRef.current) return;

      try {
        const predictions = await cocoModelRef.current.detect(video);
        const found = predictions.find((p) =>
          DEVICE_CLASSES.includes(p.class) && p.score > 0.55
        );
        if (found) {
          registerViolation(
            'device_detected',
            `Electronic device detected in frame (${found.class})`
          );
        }
      } catch (err) {
        // Silently ignore
      }
    }, PHONE_DETECT_INTERVAL_MS);

    return () => clearInterval(phoneIntervalRef.current);
  }, [enabled, modelsReady, videoRef, registerViolation]);

  // ─── Cleanup on unmount ───────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
      if (phoneIntervalRef.current) clearInterval(phoneIntervalRef.current);
    };
  }, []);

  return { violations, warningCount, terminated, modelsReady };
}
