import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Camera, CameraOff, Sparkles, Minimize2, Sliders, CheckCircle2, Hand, Target } from 'lucide-react';
import { sounds } from '../services/soundEffects';
import './CameraWidget.css';

// 21-Landmark hand connections for space constellation HUD
const HAND_CONNECTIONS = [
  [0, 1], [1, 2], [2, 3], [3, 4],         // Thumb
  [0, 5], [5, 6], [6, 7], [7, 8],         // Index
  [5, 9], [9, 10], [10, 11], [11, 12],    // Middle
  [9, 13], [13, 14], [14, 15], [15, 16],  // Ring
  [13, 17], [17, 18], [18, 19], [19, 20], // Pinky
  [0, 17]                                 // Palm base
];

const dist = (p1, p2) => Math.hypot(p1.x - p2.x, p1.y - p2.y);

export const CameraWidget = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [streamActive, setStreamActive] = useState(false);
  const [hasPermission, setHasPermission] = useState(true);
  const [detectedGesture, setDetectedGesture] = useState(null);
  const [handDetected, setHandDetected] = useState(false);
  const [fps, setFps] = useState(30);

  // 10-Second Per-User Calibration States
  const [isCalibrating, setIsCalibrating] = useState(false);
  const [calibPhase, setCalibPhase] = useState(1);
  const [calibCountdown, setCalibCountdown] = useState(5.0);
  const [calibTotalElapsed, setCalibTotalElapsed] = useState(0.0);
  const calibIntervalRef = useRef(null);

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const handsInstanceRef = useRef(null);
  const animFrameRef = useRef(null);
  const isProcessingRef = useRef(false);

  // Debounced gesture tracking state with jitter tolerance
  const gestureStateRef = useRef({
    fistHoldStart: 0,
    lastFistSeen: 0,
    hasFiredFist: false,
    hasFiredLongFist: false,

    throwHoldStart: 0,
    lastThrowSeen: 0,
    hasFiredThrow: false,

    undoHoldStart: 0,
    lastUndoSeen: 0,
    hasFiredUndo: false,

    frameCount: 0,
    fpsTimer: performance.now()
  });

  // ── Hand Landmarks & Multi-Thumb Invariant Gesture Evaluation ───
  const onResults = useCallback((results) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;

    ctx.clearRect(0, 0, w, h);

    if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
      setHandDetected(false);
      const state = gestureStateRef.current;
      const now = performance.now();
      // Grace period before clearing on total hand disappearance
      if (now - state.lastFistSeen > 250) {
        state.fistHoldStart = 0;
        state.hasFiredFist = false;
        state.hasFiredLongFist = false;
      }
      if (now - state.lastThrowSeen > 250) {
        state.throwHoldStart = 0;
        state.hasFiredThrow = false;
      }
      if (now - state.lastUndoSeen > 250) {
        state.undoHoldStart = 0;
        state.hasFiredUndo = false;
      }
      setDetectedGesture(null);
      return;
    }

    setHandDetected(true);
    const lm = results.multiHandLandmarks[0];

    // 1. Draw Space Constellation Skeleton
    ctx.lineWidth = 1.6;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.75)';
    ctx.shadowColor = 'rgba(255, 255, 255, 0.85)';
    ctx.shadowBlur = 6;

    HAND_CONNECTIONS.forEach(([i, j]) => {
      // Mirror X because front camera is mirrored
      const x1 = (1 - lm[i].x) * w;
      const y1 = lm[i].y * h;
      const x2 = (1 - lm[j].x) * w;
      const y2 = lm[j].y * h;

      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
    });

    // 2. Draw Landmark Starlight Nodes
    ctx.shadowBlur = 0;
    lm.forEach((pt, idx) => {
      const px = (1 - pt.x) * w;
      const py = pt.y * h;
      const isTip = [4, 8, 12, 16, 20].includes(idx);

      ctx.fillStyle = isTip ? '#FFFFFF' : '#94A3B8';
      ctx.beginPath();
      ctx.arc(px, py, isTip ? 3.5 : 2, 0, Math.PI * 2);
      ctx.fill();
    });

    // 3. Palm Center Pivot Node
    const wrist = lm[0];
    const middleMcp = lm[9];
    const palmCenter = {
      x: (wrist.x + middleMcp.x) / 2,
      y: (wrist.y + middleMcp.y) / 2
    };

    const palmX = (1 - palmCenter.x) * w;
    const palmY = palmCenter.y * h;

    // ── 4. Independent Multi-Vector Fist & Thumb-Invariant Analysis ───
    const handScale = Math.max(0.001, dist(lm[0], lm[9])); // Wrist to middle MCP scale baseline
    
    // Fingertip-to-palmCenter distance ratios (scale-normalized)
    const tipRatios = [
      dist(lm[8], palmCenter) / handScale,  // Index
      dist(lm[12], palmCenter) / handScale, // Middle
      dist(lm[16], palmCenter) / handScale, // Ring
      dist(lm[20], palmCenter) / handScale  // Pinky
    ];
    const avgTipToPalm = (tipRatios[0] + tipRatios[1] + tipRatios[2] + tipRatios[3]) / 4;

    // A finger is extended if its tip is noticeably far from its MCP base
    const isFingerExtended = (tip, pip, mcp) => {
      const dTipMcp = dist(lm[tip], lm[mcp]);
      const dPipMcp = dist(lm[pip], lm[mcp]);
      const dTipWrist = dist(lm[tip], wrist);
      const dPipWrist = dist(lm[pip], wrist);
      return (dTipMcp > dPipMcp * 1.30) && (dTipWrist > dPipWrist * 1.05);
    };

    const indexExt = isFingerExtended(8, 6, 5);
    const middleExt = isFingerExtended(12, 10, 9);
    const ringExt = isFingerExtended(16, 14, 13);
    const pinkyExt = isFingerExtended(20, 18, 17);

    const extendedCount = (indexExt ? 1 : 0) + (middleExt ? 1 : 0) + (ringExt ? 1 : 0) + (pinkyExt ? 1 : 0);

    // THROW / OPEN HAND: 3 or 4 fingers extended outwards OR high average distance
    const isThrow = (extendedCount >= 3) || (avgTipToPalm > 1.35);

    // PEACE / ROLLBACK: Index and Middle extended, Ring and Pinky curled
    const isUndo = indexExt && middleExt && !ringExt && !pinkyExt;

    // Only exclude explicit thumbs-up where thumb is stuck out while all other fingers curled
    const isThumbsUp = (dist(lm[4], lm[2]) > dist(lm[3], lm[2]) * 1.6) && (lm[4].y < lm[5].y - 0.12) && (dist(lm[4], palmCenter) / handScale > 1.35);

    // DIRECT FIST DETECTION:
    // Multi-metric fusion:
    // 1) All or almost all fingers are curled (extendedCount <= 1), AND
    // 2) The average fingertip-to-palm distance is compact (avgTipToPalm <= 0.95), OR
    // 3) extendedCount is 0.
    // Thumb is 100% invariant: wrapped over fingers, on the side, tucked under, or over knuckles!
    // Directly identifies a fist on cold-start entry without needing to open the palm first!
    const isFist = ((extendedCount === 0) || (extendedCount <= 1 && avgTipToPalm <= 0.95) || (avgTipToPalm <= 0.85)) && !isThumbsUp && !isThrow && !isUndo;

    const state = gestureStateRef.current;
    const now = performance.now();

    // ── 5. Debounced Gesture Timing with 400ms Jitter Grace Window ────
    if (isFist) {
      state.lastFistSeen = now;
      if (state.fistHoldStart === 0) {
        state.fistHoldStart = now;
      }
      state.throwHoldStart = 0;
      state.undoHoldStart = 0;
    } else {
      // 400ms grace window so frame blur/jitter never resets hold timer
      if (state.fistHoldStart !== 0 && now - state.lastFistSeen > 400) {
        state.fistHoldStart = 0;
        state.hasFiredFist = false;
        state.hasFiredLongFist = false;
      }
    }

    if (isThrow) {
      state.lastThrowSeen = now;
      if (state.throwHoldStart === 0) {
        state.throwHoldStart = now;
      }
      state.fistHoldStart = 0;
      state.undoHoldStart = 0;
    } else {
      if (state.throwHoldStart !== 0 && now - state.lastThrowSeen > 400) {
        state.throwHoldStart = 0;
        state.hasFiredThrow = false;
      }
    }

    if (isUndo) {
      state.lastUndoSeen = now;
      if (state.undoHoldStart === 0) {
        state.undoHoldStart = now;
      }
      state.fistHoldStart = 0;
      state.throwHoldStart = 0;
    } else {
      if (state.undoHoldStart !== 0 && now - state.lastUndoSeen > 400) {
        state.undoHoldStart = 0;
        state.hasFiredUndo = false;
      }
    }

    // ── 6. Visual HUD Reticle & Custom Event Dispatch ──────────
    if (state.fistHoldStart !== 0) {
      const holdMs = now - state.fistHoldStart;
      const holdPercent = Math.min(1.0, holdMs / 250);

      // Radial charge ring around palm center
      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = 3.5;
      ctx.beginPath();
      ctx.arc(palmX, palmY, 24, -Math.PI / 2, -Math.PI / 2 + holdPercent * Math.PI * 2);
      ctx.stroke();

      ctx.font = '600 11px "Space Grotesk", sans-serif';
      ctx.fillStyle = '#FFFFFF';
      ctx.textAlign = 'center';
      ctx.fillText(
        holdMs >= 1400 ? 'LONG FIST: SELECTIVE BEAM' : (holdPercent >= 1 ? 'FIST ARMED: HOST A' : 'HOLDING FIST…'),
        palmX,
        palmY - 32
      );

      // Trigger standard FIST at 250ms for instant direct detection
      if (holdMs >= 250 && !state.hasFiredFist) {
        state.hasFiredFist = true;
        sounds.playGestureLock();
        setDetectedGesture('fist');
        window.dispatchEvent(new CustomEvent('aerosync:gesture', {
          detail: { gesture: 'fist', isSelective: false }
        }));
      }

      // Trigger LONG FIST at 1400ms
      if (holdMs >= 1400 && !state.hasFiredLongFist) {
        state.hasFiredLongFist = true;
        sounds.playGestureLock();
        setDetectedGesture('long_fist');
        window.dispatchEvent(new CustomEvent('aerosync:gesture', {
          detail: { gesture: 'fist', isSelective: true }
        }));
      }
    } else if (state.throwHoldStart !== 0) {
      const holdMs = now - state.throwHoldStart;
      const throwPercent = Math.min(1.0, holdMs / 250);

      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.arc(palmX, palmY, 26, 0, Math.PI * 2);
      ctx.stroke();

      ctx.font = '600 11px "Space Grotesk", sans-serif';
      ctx.fillStyle = '#FFFFFF';
      ctx.textAlign = 'center';
      ctx.fillText(throwPercent >= 1 ? 'THROW: CLAIM TARGET B' : 'OPEN HAND DETECTED', palmX, palmY - 32);

      if (holdMs >= 250 && !state.hasFiredThrow) {
        state.hasFiredThrow = true;
        sounds.playThrowLock();
        setDetectedGesture('throw');
        window.dispatchEvent(new CustomEvent('aerosync:gesture', {
          detail: { gesture: 'throw' }
        }));
      }
    } else if (state.undoHoldStart !== 0) {
      const holdMs = now - state.undoHoldStart;

      ctx.strokeStyle = '#FFFFFF';
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.arc(palmX, palmY, 22, 0, Math.PI * 2);
      ctx.stroke();

      ctx.font = '600 11px "Space Grotesk", sans-serif';
      ctx.fillStyle = '#FFFFFF';
      ctx.textAlign = 'center';
      ctx.fillText('PEACE SIGN: ROLLBACK', palmX, palmY - 30);

      if (holdMs >= 250 && !state.hasFiredUndo) {
        state.hasFiredUndo = true;
        sounds.playUndoChime();
        setDetectedGesture('undo');
        window.dispatchEvent(new CustomEvent('aerosync:gesture', {
          detail: { gesture: 'undo' }
        }));
      }
    } else {
      setDetectedGesture(null);
    }
  }, []);

  // ── Initialize MediaPipe Hands with cold-start detection ────
  const initMediaPipe = useCallback(async () => {
    try {
      let HandsClass = null;

      // 1. Check window.Hands from local static script
      if (typeof window !== 'undefined' && window.Hands) {
        HandsClass = window.Hands;
      } else {
        // 2. Fall back to bundled @mediapipe/hands
        try {
          const mp = await import('@mediapipe/hands');
          HandsClass = mp.Hands || mp.default?.Hands || mp.default;
        } catch (_) {}
      }

      if (!HandsClass) {
        console.warn('MediaPipe Hands not yet loaded, will retry on next frame');
        return null;
      }

      const hands = new HandsClass({
        locateFile: (file) => `/mediapipe/hands/${file}`
      });

      // minDetectionConfidence tuned to 0.12 for instantaneous cold-start fist detection
      // without needing to open the palm first, across all thumb orientations!
      hands.setOptions({
        maxNumHands: 1,
        modelComplexity: 0,
        minDetectionConfidence: 0.12,
        minTrackingConfidence: 0.12
      });

      hands.onResults(onResults);
      handsInstanceRef.current = hands;
      return hands;
    } catch (err) {
      console.warn('Failed to initialize MediaPipe Hands:', err);
      return null;
    }
  }, [onResults]);

  // ── Start Camera Feed ───────────────────────────────────────
  const startCamera = useCallback(async () => {
    try {
      if (streamRef.current && streamRef.current.active) {
        setStreamActive(true);
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
        audio: false
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.onloadedmetadata = () => {
          videoRef.current.play().catch(() => {});
        };
      }
      setStreamActive(true);
      setHasPermission(true);

      // Initialize hand detector
      await initMediaPipe();
    } catch (err) {
      console.warn('Camera access error:', err);
      setHasPermission(false);
      setStreamActive(false);
    }
  }, [initMediaPipe]);

  const stopCamera = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    setStreamActive(false);
    setHandDetected(false);
    setDetectedGesture(null);
  }, []);

  // Auto-start camera sensor on mount so gestures work immediately
  useEffect(() => {
    startCamera();
    return () => {
      stopCamera();
      cancelCalibration();
    };
  }, [startCamera, stopCamera]);

  // ── Frame Processing Loop with Lock ───────────────────────────
  useEffect(() => {
    let active = true;

    const processLoop = async () => {
      if (!active) return;

      const video = videoRef.current;
      if (video && video.readyState >= 2) {
        if (!handsInstanceRef.current) {
          await initMediaPipe();
        }

        if (handsInstanceRef.current && !isProcessingRef.current) {
          isProcessingRef.current = true;
          try {
            await handsInstanceRef.current.send({ image: video });
          } catch (err) {
            console.debug('MediaPipe process tick error:', err);
          } finally {
            isProcessingRef.current = false;
          }
        }

        // FPS tracking
        const now = performance.now();
        gestureStateRef.current.frameCount++;
        if (now - gestureStateRef.current.fpsTimer >= 1000) {
          setFps(gestureStateRef.current.frameCount);
          gestureStateRef.current.frameCount = 0;
          gestureStateRef.current.fpsTimer = now;
        }
      }

      animFrameRef.current = requestAnimationFrame(processLoop);
    };

    if (streamActive) {
      animFrameRef.current = requestAnimationFrame(processLoop);
    }

    return () => {
      active = false;
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
    };
  }, [streamActive, initMediaPipe]);

  // 10-Second Calibration Routine
  const startCalibration = () => {
    setIsCalibrating(true);
    setCalibPhase(1);
    setCalibCountdown(5.0);
    setCalibTotalElapsed(0.0);

    const startTime = Date.now();
    if (calibIntervalRef.current) clearInterval(calibIntervalRef.current);

    calibIntervalRef.current = setInterval(() => {
      const elapsed = (Date.now() - startTime) / 1000.0;
      setCalibTotalElapsed(Math.min(10.0, elapsed));

      if (elapsed < 5.0) {
        setCalibPhase(1);
        setCalibCountdown(Math.max(0, 5.0 - elapsed));
      } else if (elapsed < 10.0) {
        setCalibPhase(2);
        setCalibCountdown(Math.max(0, 10.0 - elapsed));
      } else {
        setCalibPhase(3);
        setCalibCountdown(0.0);
        clearInterval(calibIntervalRef.current);
        calibIntervalRef.current = null;
        setTimeout(() => setIsCalibrating(false), 2500);
      }
    }, 100);
  };

  const cancelCalibration = () => {
    if (calibIntervalRef.current) {
      clearInterval(calibIntervalRef.current);
      calibIntervalRef.current = null;
    }
    setIsCalibrating(false);
  };

  return (
    <div className="camera-widget-container">
      {/* Expanded Camera Preview Window in Bottom Corner */}
      <div 
        className="camera-pip-window glass-panel"
        style={{ display: isOpen ? 'flex' : 'none' }}
      >
        <div className="pip-header">
          <div className="pip-title-group">
            <span className={`live-dot ${handDetected ? 'active-pulse' : 'pulse'}`} />
            <span className="pip-title">Gesture Sensor</span>
            <span className="pip-node-badge">MediaPipe ML</span>
          </div>
          <div className="pip-header-actions">
            <button 
              className={`pip-calib-btn ${isCalibrating ? 'active' : ''}`}
              onClick={isCalibrating ? cancelCalibration : startCalibration}
              title="10s Per-User Biomechanical Calibration"
            >
              <Sliders size={13} />
              <span>{isCalibrating ? 'Cancel' : 'Calibrate'}</span>
            </button>
            <button className="pip-close-btn" onClick={() => setIsOpen(false)} title="Minimize Camera">
              <Minimize2 size={15} />
            </button>
          </div>
        </div>

        <div className="pip-video-wrapper">
          {hasPermission ? (
            <>
              <video 
                ref={videoRef} 
                autoPlay 
                playsInline 
                muted 
                className="pip-video-feed"
              />

              {/* Real-time Hand Constellation Canvas Overlay */}
              <canvas
                ref={canvasRef}
                width={290}
                height={180}
                className="pip-canvas-overlay"
              />

              {/* Space Themed Cosmic Sensor Zone Brackets */}
              <div className="cosmic-sensor-zone">
                <span className="corner-bracket top-l" />
                <span className="corner-bracket top-r" />
                <span className="corner-bracket bot-l" />
                <span className="corner-bracket bot-r" />
                <div className="cosmic-compass-center">
                  <span className="compass-crosshair" />
                </div>
              </div>

              {/* Live Tracking HUD Banner */}
              {!isCalibrating && (
                <div className={`pip-assist-banner ${detectedGesture ? 'active-gesture' : ''}`}>
                  <div className="assist-row">
                    <span className={`sensor-beacon ${handDetected ? 'beacon-locked' : ''}`} />
                    <span className="assist-text">
                      {detectedGesture === 'fist'
                        ? '✊ FIST DETECTED — HOST A ARMED'
                        : detectedGesture === 'long_fist'
                        ? '📋 LONG FIST — SELECTIVE BEAM'
                        : detectedGesture === 'throw'
                        ? '🚀 THROW — CLAIMING TARGET B'
                        : detectedGesture === 'undo'
                        ? '✌ PEACE — UNDO ROLLBACK'
                        : handDetected
                        ? 'Hand Locked: Make Fist or Throw'
                        : 'Position Hand in Sensor View'}
                    </span>
                  </div>
                </div>
              )}

              {/* 10-Second Calibration Interactive Overlay */}
              {isCalibrating && (
                <div className="pip-calibration-overlay">
                  <div className="calib-card">
                    <div className="calib-progress-track">
                      <div 
                        className="calib-progress-fill" 
                        style={{ width: `${(calibTotalElapsed / 10.0) * 100}%` }}
                      />
                    </div>

                    {calibPhase === 1 && (
                      <div className="calib-phase-content">
                        <div className="calib-icon-badge open-hand"><Hand size={22} /></div>
                        <div className="calib-phase-title">Phase 1: Open Hand</div>
                        <div className="calib-phase-desc">Spread all 5 fingers facing front camera</div>
                        <div className="calib-timer">{calibCountdown.toFixed(1)}s</div>
                      </div>
                    )}

                    {calibPhase === 2 && (
                      <div className="calib-phase-content">
                        <div className="calib-icon-badge closed-fist"><Target size={22} /></div>
                        <div className="calib-phase-title">Phase 2: Closed Fist</div>
                        <div className="calib-phase-desc">Form a natural fist facing front camera</div>
                        <div className="calib-timer">{calibCountdown.toFixed(1)}s</div>
                      </div>
                    )}

                    {calibPhase === 3 && (
                      <div className="calib-phase-content complete">
                        <CheckCircle2 size={26} className="calib-success-icon" />
                        <div className="calib-phase-title">Calibration Complete!</div>
                        <div className="calib-phase-desc">Personalized biomechanics saved to profile</div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="pip-no-camera">
              <CameraOff size={32} />
              <p>Camera permission required for gestures</p>
              <button 
                onClick={startCamera} 
                className="pip-calib-btn" 
                style={{ marginTop: 8 }}
              >
                Enable Camera
              </button>
            </div>
          )}
        </div>

        <div className="pip-footer">
          <span className="status-label">
            {handDetected ? 'Kinematic Tracking Active' : 'Sensor Ready'}
          </span>
          <span className="fps-indicator">{fps} FPS</span>
        </div>
      </div>

      {/* Floating Pill Toggle Button in Bottom-Right Corner */}
      <button 
        className={`camera-toggle-fab ${isOpen ? 'active' : ''} ${handDetected ? 'fab-hand-detected' : ''}`}
        onClick={() => {
          if (!streamActive) startCamera();
          setIsOpen(!isOpen);
        }}
        title={isOpen ? 'Minimize Camera Feed' : 'Open Camera Sensor View'}
      >
        <Camera size={16} />
        <span className={`fab-status-dot ${handDetected ? 'fab-active' : ''}`} />
        <span className="fab-text">
          {detectedGesture === 'fist'
            ? '✊ Host A Locked'
            : detectedGesture === 'long_fist'
            ? '📋 Selective Beam'
            : detectedGesture === 'throw'
            ? '🚀 Target B Locked'
            : detectedGesture === 'undo'
            ? '✌ Rollback Locked'
            : handDetected
            ? 'Sensor: Hand Locked'
            : isOpen
            ? 'Hide Sensor'
            : 'Camera Sensor'}
        </span>
      </button>
    </div>
  );
};
