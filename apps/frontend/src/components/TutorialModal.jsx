import React, { useState } from 'react';
import {
  X, BookOpen, Hand, Target, Maximize2, Zap,
  Globe, RefreshCw, Send, CheckCircle2, Shield, AlertTriangle,
  Info, Laptop, Sparkles
} from 'lucide-react';
import { Button } from './Button';
import './TutorialModal.css';

export const TutorialModal = ({ isOpen, onClose }) => {
  const [activeTab, setActiveTab] = useState('gestures');

  if (!isOpen) return null;

  return (
    <div className="tutorial-overlay" onClick={onClose}>
      <div className="tutorial-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="tutorial-header">
          <div className="tutorial-title">
            <BookOpen size={18} color="#FFFFFF" />
            <h2>AeroSync Walkthrough & System Guide</h2>
            <span className="tutorial-badge">v2.4 Stealth</span>
          </div>
          <button className="tutorial-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="tutorial-tabs">
          <button
            className={`tutorial-tab-btn ${activeTab === 'gestures' ? 'active' : ''}`}
            onClick={() => setActiveTab('gestures')}
          >
            <Hand size={14} style={{ marginRight: 6 }} />
            Gestures (Fist & Throw)
          </button>
          <button
            className={`tutorial-tab-btn ${activeTab === 'coordinates' ? 'active' : ''}`}
            onClick={() => setActiveTab('coordinates')}
          >
            <Maximize2 size={14} style={{ marginRight: 6 }} />
            Screen Coordinates & Layout
          </button>
          <button
            className={`tutorial-tab-btn ${activeTab === 'chrome' ? 'active' : ''}`}
            onClick={() => setActiveTab('chrome')}
          >
            <Globe size={14} style={{ marginRight: 6 }} />
            Chrome Auto-Launcher
          </button>
          <button
            className={`tutorial-tab-btn ${activeTab === 'tray' ? 'active' : ''}`}
            onClick={() => setActiveTab('tray')}
          >
            <Laptop size={14} style={{ marginRight: 6 }} />
            System Tray & Auto-Start
          </button>
        </div>

        {/* Content Body */}
        <div className="tutorial-body">
          {activeTab === 'gestures' && (
            <div>
              <div className="tutorial-section-title">Kinematic Hand Gestures</div>
              <p className="tutorial-desc">
                AeroSync operates using front-view camera gestures. Every computer runs the exact same software — any PC can become Host A, and any peer can become Target B.
              </p>

              <div className="tutorial-card-grid">
                <div className="tutorial-card">
                  <div className="tutorial-card-icon"><Hand size={22} color="#FB923C" /></div>
                  <h4>FIST Gesture — Arm Host A</h4>
                  <p>
                    Face your palm to the front camera and close your fist. Hold for at least <strong>600ms</strong>. This PC becomes Host A, captures all open windows, tabs, and clipboard, and notifies your Constellation peers.
                  </p>
                </div>

                <div className="tutorial-card">
                  <div className="tutorial-card-icon"><Send size={22} color="#38BDF8" /></div>
                  <h4>THROW Gesture — Claim Target B</h4>
                  <p>
                    On any Candidate computer, thrust your open hand toward the camera. This PC immediately becomes Target B, claims the workspace from Host A, and reconstructs it.
                  </p>
                </div>
              </div>

              <div className="tutorial-highlight-box">
                <Shield size={16} color="#34D399" style={{ display: 'inline-block', verticalAlign: 'middle', marginRight: 6 }} />
                <strong>Privacy Assurance:</strong> Node-based skeleton lines are calculated in memory and never rendered over your video feed.
              </div>
            </div>
          )}

          {activeTab === 'coordinates' && (
            <div>
              <div className="tutorial-section-title">Screen Orientation & Grid Division</div>
              <p className="tutorial-desc">
                AeroSync maps your display into normalized relative coordinates (0.0 to 1.0) so application layouts look visually identical between computers, even if they have different resolutions (e.g. 4K vs 1080p).
              </p>

              <div className="tutorial-card-grid">
                <div className="tutorial-card">
                  <div className="tutorial-card-icon"><Maximize2 size={22} color="#C084FC" /></div>
                  <h4>Proportional Scaling</h4>
                  <p>
                    Windows are placed in the exact same quadrant (top-left, half-screen, full-screen) relative to Target B's screen size.
                  </p>
                </div>

                <div className="tutorial-card">
                  <div className="tutorial-card-icon"><Zap size={22} color="#38BDF8" /></div>
                  <h4>Smart Window Reuse</h4>
                  <p>
                    If an application is already open on Target B, AeroSync avoids relaunching it from scratch — it simply reorients and moves the window to match Host A.
                  </p>
                </div>
              </div>

              <div className="tutorial-highlight-box">
                <AlertTriangle size={16} color="#FB923C" style={{ display: 'inline-block', verticalAlign: 'middle', marginRight: 6 }} />
                <strong>Unachieved Items Notification:</strong> If an application is not installed on Target B, AeroSync will relaunch all other items and notify you with the list of missing apps.
              </div>
            </div>
          )}

          {activeTab === 'chrome' && (
            <div>
              <div className="tutorial-section-title">Automated Google Chrome Sync</div>
              <p className="tutorial-desc">
                No manual flags needed. AeroSync features an auto-launcher that detects your standard Google Chrome installation and syncs open tabs smoothly.
              </p>

              <div className="tutorial-card-grid">
                <div className="tutorial-card">
                  <div className="tutorial-card-icon"><Globe size={22} color="#38BDF8" /></div>
                  <h4>One-Click Launch</h4>
                  <p>
                    All transferred tabs are grouped into a clean, new Chrome window automatically.
                  </p>
                </div>

                <div className="tutorial-card">
                  <div className="tutorial-card-icon"><RefreshCw size={22} color="#34D399" /></div>
                  <h4>Tab Deduplication</h4>
                  <p>
                    Tabs that are already open on Target B are skipped and reused to prevent clutter and memory waste.
                  </p>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'tray' && (
            <div>
              <div className="tutorial-section-title">System Tray & Auto-Start on Login</div>
              <p className="tutorial-desc">
                AeroSync sits quietly in your Windows taskbar notification area, ready to respond to gestures instantly.
              </p>

              <div className="tutorial-card-grid">
                <div className="tutorial-card">
                  <div className="tutorial-card-icon"><Send size={22} color="#38BDF8" /></div>
                  <h4>Auto-Start at Login</h4>
                  <p>
                    Toggle "Start at Windows Login" directly from the system tray menu to have AeroSync active whenever you boot your PC.
                  </p>
                </div>

                <div className="tutorial-card">
                  <div className="tutorial-card-icon"><Sparkles size={22} color="#C084FC" /></div>
                  <h4>Cosmic Indicator</h4>
                  <p>
                    The tray icon glows cyan when ready, gold when Host A is armed, and green when workspace transfer completes.
                  </p>
                </div>
              </div>

              <div className="tutorial-highlight-box">
                <Info size={16} color="#38BDF8" style={{ display: 'inline-block', verticalAlign: 'middle', marginRight: 6 }} />
                <strong>Tip:</strong> You can right-click the AeroSync icon in your taskbar anytime for manual fallback triggers or to launch Chrome.
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="tutorial-footer">
          <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
            AeroSync Constellation System • Self-Hosted & Free
          </span>
          <Button variant="primary" size="md" onClick={onClose}>
            Got It!
          </Button>
        </div>
      </div>
    </div>
  );
};
