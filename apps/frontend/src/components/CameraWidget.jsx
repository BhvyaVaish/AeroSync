import React, { useState, useRef, useEffect } from 'react';
import { Camera, CameraOff, Sparkles, Minimize2, Sliders, CheckCircle2, X } from 'lucide-react';
import './CameraWidget.css';

export const CameraWidget = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [streamActive, setStreamActive] = useState(false);
  const [hasPermission, setHasPermission] = useState(true);
  const videoRef = useRef(null);
  const streamRef = useRef(null);

  // 10-Second Per-User Calibration States
  const [isCalibrating, setIsCalibrating] = useState(false);
  const [calibPhase, setCalibPhase] = useState(1); // 1 = Open Hand (5s), 2 = Fist (5s), 3 = Done
  const [calibCountdown, setCalibCountdown] = useState(5.0);
  const [calibTotalElapsed, setCalibTotalElapsed] = useState(0.0);
  const calibIntervalRef = useRef(null);

  const startCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
        audio: false
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setStreamActive(true);
      setHasPermission(true);
    } catch (err) {
      console.warn('Camera access error:', err);
      setHasPermission(false);
      setStreamActive(false);
    }
  };

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    setStreamActive(false);
  };

  useEffect(() => {
    if (isOpen) {
      startCamera();
    } else {
      stopCamera();
      cancelCalibration();
    }
    return () => {
      stopCamera();
      cancelCalibration();
    };
  }, [isOpen]);

  // 10-Second Calibration Routine
  const startCalibration = async () => {
    // Notify backend gesture engine
    try {
      fetch('http://localhost:7878/calibrate/start', { method: 'POST' }).catch(() => {});
    } catch (_) {}

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
        // Complete
        setCalibPhase(3);
        setCalibCountdown(0.0);
        clearInterval(calibIntervalRef.current);
        calibIntervalRef.current = null;

        // Auto dismiss after 2.5s
        setTimeout(() => {
          setIsCalibrating(false);
        }, 2500);
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
      {isOpen && (
        <div className="camera-pip-window glass-panel">
          <div className="pip-header">
            <div className="pip-title-group">
              <span className="live-dot pulse" />
              <span className="pip-title">AeroSync Sensor</span>
              <span className="pip-node-badge">Cosmic HUD</span>
            </div>
            <div className="pip-header-actions">
              <button 
                className={`pip-calib-btn ${isCalibrating ? 'active' : ''}`}
                onClick={isCalibrating ? cancelCalibration : startCalibration}
                title="10s Per-User Biomechanical Calibration"
              >
                <Sliders size={13} />
                <span>{isCalibrating ? 'Cancel' : '10s Calibrate'}</span>
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

                {/* Assistive Guide Overlay */}
                {!isCalibrating && (
                  <div className="pip-assist-banner">
                    <div className="assist-row">
                      <span className="sensor-beacon" />
                      <span className="assist-text">Detection Zone: Keep hand inside brackets</span>
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
                          <div className="calib-icon-badge open-hand">🖐️</div>
                          <div className="calib-phase-title">Phase 1: Open Hand</div>
                          <div className="calib-phase-desc">Spread all 5 fingers facing front camera</div>
                          <div className="calib-timer">{calibCountdown.toFixed(1)}s</div>
                        </div>
                      )}

                      {calibPhase === 2 && (
                        <div className="calib-phase-content">
                          <div className="calib-icon-badge closed-fist">✊</div>
                          <div className="calib-phase-title">Phase 2: Closed Fist</div>
                          <div className="calib-phase-desc">Form a natural fist facing front camera</div>
                          <div className="calib-timer">{calibCountdown.toFixed(1)}s</div>
                        </div>
                      )}

                      {calibPhase === 3 && (
                        <div className="calib-phase-content complete">
                          <CheckCircle2 size={26} className="calib-success-icon" />
                          <div className="calib-phase-title">Calibration Complete!</div>
                          <div className="calib-phase-desc">Personalized biomechanics saved to profile ✦</div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="pip-no-camera">
                <CameraOff size={32} />
                <p>Camera permission denied or camera disconnected</p>
              </div>
            )}

            {/* Top Cosmic Mode Badge */}
            {!isCalibrating && (
              <div className="pip-tracking-overlay">
                <Sparkles size={12} className="sparkle-icon" />
                <span>Kinematic Lock Armed</span>
              </div>
            )}
          </div>

          <div className="pip-footer">
            <span className="status-label">
              {isCalibrating ? 'Calibrating Biometrics…' : 'Ready for Fist / Throw'}
            </span>
            <span className="fps-indicator">30 FPS</span>
          </div>
        </div>
      )}

      {/* Floating Pill Toggle Button in Bottom-Right Corner */}
      <button 
        className={`camera-toggle-fab ${isOpen ? 'active' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        title={isOpen ? 'Minimize Camera Feed' : 'Open Camera Sensor View'}
      >
        <Camera size={20} />
        <span className="fab-status-dot" />
        <span className="fab-text">{isOpen ? 'Hide Cam' : 'Camera'}</span>
      </button>
    </div>
  );
};
