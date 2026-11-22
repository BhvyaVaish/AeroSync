import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { GlassCard } from '../components/GlassCard';
import { Button } from '../components/Button';
import { TutorialModal } from '../components/TutorialModal';
import { QueueMonitorWidget } from '../components/QueueMonitorWidget';
import { SelectiveTransferModal } from '../components/SelectiveTransferModal';
import {
  MonitorSmartphone, CloudUpload, Link as LinkIcon, Power,
  CheckCircle, XCircle, Clock, Zap, Radio, BookOpen, CheckSquare,
  AlertTriangle, Keyboard, Battery, BatteryCharging,
  Target, Hand, ArrowRightLeft, Send, RotateCcw, Activity
} from 'lucide-react';
import { api } from '../services/api';
import { useWebSocket } from '../services/websocket';
import { sounds } from '../services/soundEffects';
import './Dashboard.css';

// Role state display config (mirrors shared/constants.py RoleState with matte aesthetic tones)
const ROLE_CONFIG = {
  neutral:      { label: 'NEUTRAL',                  color: '#94A3B8', bg: 'var(--status-neutral-bg)', bd: 'var(--status-neutral-bd)', Icon: Radio,          tip: 'Awaiting gesture input to initialize Host A (Fist)' },
  host:         { label: 'HOST A — Capturing',        color: '#FB923C', bg: 'var(--status-host-bg)', bd: 'var(--status-host-bd)', Icon: Hand,           tip: 'Workspace capture in progress — Waiting for Target B or launch' },
  candidate:    { label: 'CANDIDATE — Ready to Claim',color: '#38BDF8', bg: 'var(--status-candidate-bg)', bd: 'var(--status-candidate-bd)', Icon: Target,         tip: 'Execute throw gesture to claim Target B' },
  target:       { label: 'TARGET B — Receiving',      color: '#C084FC', bg: 'var(--status-target-bg)', bd: 'var(--status-target-bd)', Icon: Send,           tip: 'Workspace payload arriving — Reconstructing state' },
  transferring: { label: 'TRANSFERRING…',             color: '#34D399', bg: 'var(--status-transferring-bg)', bd: 'var(--status-transferring-bd)', Icon: ArrowRightLeft, tip: 'P2P data synchronization in transit' },
};

export const Dashboard = () => {
  const navigate = useNavigate();
  const { onlineDevices, connectionStatus, connect, sendMessage, lastMessage } = useWebSocket();
  const [devices, setDevices] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [roleState, setRoleState] = useState('neutral');
  const [hostPeer, setHostPeer] = useState(null);   // which peer is currently Host A
  const [showTutorial, setShowTutorial] = useState(window.location.hash === '#tutorial');
  const [showChecklist, setShowChecklist] = useState(window.location.hash === '#checklist');
  const [shortcutToast, setShortcutToast] = useState(null);
  const [batteryState, setBatteryState] = useState(null);
  const [lastDetectedGesture, setLastDetectedGesture] = useState(null);

  // Monitor battery state for Eco-Mode
  useEffect(() => {
    let batteryInstance = null;
    let onLevelChange = null;
    let onChargingChange = null;

    if (typeof navigator !== 'undefined' && 'getBattery' in navigator) {
      navigator.getBattery().then((battery) => {
        batteryInstance = battery;
        const updateStatus = () => {
          const level = Math.round(battery.level * 100);
          const charging = battery.charging;
          const eco = !charging; // On battery = Eco-Mode active
          setBatteryState({ level, charging, eco });
        };
        updateStatus();
        onLevelChange = updateStatus;
        onChargingChange = updateStatus;
        battery.addEventListener('levelchange', onLevelChange);
        battery.addEventListener('chargingchange', onChargingChange);
      }).catch(() => {});
    }

    return () => {
      if (batteryInstance) {
        if (onLevelChange) batteryInstance.removeEventListener('levelchange', onLevelChange);
        if (onChargingChange) batteryInstance.removeEventListener('chargingchange', onChargingChange);
      }
    };
  }, []);

  const activeDevice = devices.length > 0 ? devices[0] : null;

  // ── Unified Role Action Triggers ─────────────────────────────
  const triggerHostA = useCallback((isSelective = false) => {
    setRoleState('host');
    setHostPeer(activeDevice?.device_id || 'local-host');
    setLastDetectedGesture(isSelective ? 'long_fist' : 'fist');
    sounds.playGestureLock();

    if (isSelective) {
      setShowChecklist(true);
      setShortcutToast({
        title: '📋 Selective Beam Armed (Long Fist)',
        desc: 'Host A Mode Activated — Select workspace elements to transmit'
      });
      sendMessage({
        type: 'host_announcing',
        device_id: activeDevice?.device_id || 'local-host',
        is_selective: true
      });
    } else {
      setShortcutToast({
        title: '✊ Host A Mode Activated (Fist)',
        desc: 'Workspace elements captured & enqueued for transmission'
      });
      sendMessage({
        type: 'host_announcing',
        device_id: activeDevice?.device_id || 'local-host',
        is_selective: false
      });
    }

    setTimeout(() => setShortcutToast(null), 4000);
  }, [activeDevice, sendMessage]);

  const triggerTargetB = useCallback(() => {
    setRoleState('target');
    setLastDetectedGesture('throw');
    sounds.playThrowLock();

    setShortcutToast({
      title: '🚀 Target B Mode Activated (Throw)',
      desc: 'Claiming workspace payload from Host A'
    });
    sendMessage({
      type: 'target_claiming',
      device_id: activeDevice?.device_id || 'local-target'
    });

    // Simulate transfer progress -> complete
    setTimeout(() => {
      setRoleState('transferring');
    }, 1200);

    setTimeout(() => {
      sounds.playTransferSuccess();
      setShortcutToast({
        title: '⚡ Transfer Synchronized',
        desc: 'Workspace reconstructed successfully on this computer'
      });
      setRoleState('neutral');
    }, 4500);

    setTimeout(() => setShortcutToast(null), 4000);
  }, [activeDevice, sendMessage]);

  const triggerRollback = useCallback(() => {
    setRoleState('neutral');
    setHostPeer(null);
    setLastDetectedGesture('undo');
    sounds.playUndoChime();

    setShortcutToast({
      title: '✌ Workspace Rollback Activated',
      desc: 'Constellation state restored to pre-transfer baseline'
    });
    sendMessage({ type: 'constellation_reset' });

    setTimeout(() => setShortcutToast(null), 4000);
  }, [sendMessage]);

  // ── Listen to in-browser MediaPipe gesture events ────────────
  useEffect(() => {
    const handleGestureEvent = (e) => {
      const { gesture, isSelective } = e.detail || {};
      if (gesture === 'fist') {
        triggerHostA(isSelective);
      } else if (gesture === 'throw') {
        triggerTargetB();
      } else if (gesture === 'undo') {
        triggerRollback();
      }
    };

    window.addEventListener('aerosync:gesture', handleGestureEvent);
    return () => window.removeEventListener('aerosync:gesture', handleGestureEvent);
  }, [triggerHostA, triggerTargetB, triggerRollback]);

  // Global browser fallback hotkey listener (Ctrl+Alt+C for Host A, Ctrl+Alt+L for Target B, Ctrl+Alt+Z for Undo)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.ctrlKey && e.altKey) {
        const key = e.key.toLowerCase();
        if (key === 'c') {
          e.preventDefault();
          triggerHostA(false);
        } else if (key === 'l' || key === 't') {
          e.preventDefault();
          triggerTargetB();
        } else if (key === 'z') {
          e.preventDefault();
          triggerRollback();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [triggerHostA, triggerTargetB, triggerRollback]);

  useEffect(() => {
    const handleHashChange = () => {
      if (window.location.hash === '#tutorial') {
        setShowTutorial(true);
      }
      if (window.location.hash === '#checklist') {
        setShowChecklist(true);
      }
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [devsRes, sessRes] = await Promise.all([
          api.devices.list(),
          api.sessions.history(5),
        ]);
        setDevices(devsRes.devices || []);
        setSessions(sessRes.sessions || []);
        if (devsRes.devices && devsRes.devices.length > 0) {
          connect(devsRes.devices[0].device_id);
        }
      } catch (err) {
        console.error('Failed to load dashboard data', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [connect]);

  // Listen to WS messages to update role state in real time
  useEffect(() => {
    if (!lastMessage) return;
    const { type, device_id } = lastMessage;
    if (type === 'host_announcing') {
      setHostPeer(device_id);
      setRoleState('candidate');
    } else if (type === 'target_claiming') {
      setRoleState('transferring');
    } else if (type === 'constellation_reset') {
      setRoleState('neutral');
      setHostPeer(null);
    } else if (type === 'workspace_ready') {
      setRoleState('target');
    }
  }, [lastMessage]);

  if (loading) {
    return <div className="dashboard-loading">Loading Dashboard...</div>;
  }

  const role = ROLE_CONFIG[roleState] || ROLE_CONFIG.neutral;

  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <div>
          <div className="pill-badge">
            <span className="pill-dot" />
            <span>WORKSPACE SYNCHRONIZATION</span>
          </div>
          <h1>Workspace Overview</h1>
          <p className="subtitle">Manage your paired devices and active sessions</p>
        </div>
        <div style={{ display: 'flex', gap: '0.65rem', alignItems: 'center', flexWrap: 'wrap' }}>
          {batteryState && (
            <div
              className={`eco-badge ${batteryState.eco ? 'eco-active' : 'eco-plugged'}`}
              title={batteryState.eco ? 'On battery power — background capture throttled' : 'Connected to AC power'}
            >
              {batteryState.charging ? <BatteryCharging size={14} /> : <Battery size={14} />}
              <span>{batteryState.level}% {batteryState.eco ? '• Eco' : '• AC'}</span>
            </div>
          )}
          <Button
            variant="primary"
            size="md"
            icon={<CheckSquare size={15} />}
            onClick={() => triggerHostA(true)}
          >
            Selective Beam
          </Button>
          <Button
            variant="secondary"
            size="md"
            icon={<BookOpen size={15} />}
            onClick={() => setShowTutorial(true)}
          >
            Walkthrough Guide
          </Button>
        </div>
      </div>

      {/* ── Shortcut Toast Popup ───────────────────────────────────────── */}
      {shortcutToast && (
        <div className="shortcut-active-toast glass-panel">
          <Keyboard size={18} />
          <div>
            <div style={{ color: '#FFFFFF', fontWeight: 700 }}>{shortcutToast.title}</div>
            <div style={{ fontSize: '0.78rem', color: '#D4D4D8' }}>{shortcutToast.desc}</div>
          </div>
        </div>
      )}

      {/* ── Sensor & Camera Fallback Shortcut Banner ────────── */}
      <div className="sensor-shortcut-banner">
        <div className="sensor-shortcut-info">
          <Activity size={18} className="sensor-alert-icon" />
          <div className="sensor-alert-text">
            <strong>Kinematic Sensor:</strong>{' '}
            {lastDetectedGesture ? (
              <span style={{ color: '#FFFFFF', fontWeight: 600 }}>
                {lastDetectedGesture.toUpperCase()} DETECTED — Computer Status Updated
              </span>
            ) : (
              <span>Live &amp; Ready • Form Fist (Host A), Throw (Target B), or Peace (Undo)</span>
            )}
          </div>
        </div>
        <div className="shortcut-pill-group">
          <button 
            className="shortcut-pill" 
            onClick={() => triggerHostA(false)} 
            title="Click or press Ctrl+Alt+C to trigger Host A"
            style={{ cursor: 'pointer', background: roleState === 'host' ? 'rgba(251, 146, 60, 0.25)' : undefined }}
          >
            Ctrl + Alt + C (Host A)
          </button>
          <span style={{ color: '#64748b' }}>•</span>
          <button 
            className="shortcut-pill" 
            onClick={() => triggerTargetB()} 
            title="Click or press Ctrl+Alt+L to trigger Target B"
            style={{ cursor: 'pointer', background: roleState === 'target' ? 'rgba(192, 132, 252, 0.25)' : undefined }}
          >
            Ctrl + Alt + L (Target B)
          </button>
          <span style={{ color: '#64748b' }}>•</span>
          <button 
            className="shortcut-pill" 
            onClick={() => triggerRollback()} 
            title="Click or press Ctrl+Alt+Z to trigger Undo"
            style={{ cursor: 'pointer' }}
          >
            Ctrl + Alt + Z (Undo)
          </button>
        </div>
      </div>

      {/* ── Role Status Banner (Matte & Glassmorphism) ───────────────────── */}
      <div
        className="role-banner"
        style={{
          borderLeft: `3px solid ${role.color}`,
          background: role.bg || 'rgba(255,255,255,0.03)',
          borderColor: role.bd || 'rgba(255,255,255,0.08)',
        }}
      >
        <span className="role-icon" style={{ color: role.color }}>
          {role.Icon ? <role.Icon size={18} /> : <Radio size={18} />}
        </span>
        <div className="role-text">
          <strong style={{ color: role.color }}>{role.label}</strong>
          <span className="role-tip">{role.tip}</span>
        </div>
        {hostPeer && (
          <span className="role-peer-badge">
            <Radio size={12} style={{ marginRight: 4 }} />
            Host: {hostPeer.substring(0, 8)}…
          </span>
        )}
      </div>
      {/* ─────────────────────────────────────────────────────────────────── */}

      {/* ── Space-Themed Queue Size Monitor ─────────────────────────────── */}
      <div style={{ marginBottom: '1.5rem' }}>
        <QueueMonitorWidget />
      </div>
      {/* ─────────────────────────────────────────────────────────────────── */}

      <div className="dashboard-grid">
        <GlassCard className="status-card" hoverEffect>
          <div className="card-header">
            <h3>Computer Status</h3>
            <span 
              className={`status-indicator ${roleState !== 'neutral' ? 'online active-glow' : connectionStatus === 'connected' ? 'online' : 'online'}`}
              style={{
                backgroundColor: roleState === 'host' ? '#FB923C' : roleState === 'target' ? '#C084FC' : roleState === 'transferring' ? '#34D399' : '#38BDF8',
                boxShadow: `0 0 10px ${roleState === 'host' ? '#FB923C' : roleState === 'target' ? '#C084FC' : roleState === 'transferring' ? '#34D399' : '#38BDF8'}`
              }}
            />
          </div>
          <div className="device-info">
            <MonitorSmartphone size={48} className="device-icon" style={{ color: role.color }} />
            <div>
              <h2>{activeDevice ? activeDevice.device_name : 'This PC (Local Host)'}</h2>
              <p style={{ color: role.color, fontWeight: 500 }}>
                {roleState === 'host'
                  ? 'Host A • Capturing & Transmitting'
                  : roleState === 'target'
                  ? 'Target B • Claimed & Receiving'
                  : roleState === 'transferring'
                  ? 'P2P Transfer • In Transit'
                  : roleState === 'candidate'
                  ? 'Candidate • Ready to Claim'
                  : 'Standby • Kinematic Sensor Active'}
              </p>
              <div style={{ fontSize: '0.72rem', color: '#94A3B8', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
                {activeDevice?.platform || 'Windows 11'} • Sensor: {lastDetectedGesture ? `${lastDetectedGesture.toUpperCase()} LOCKED` : 'TRACKING'}
              </div>
            </div>
          </div>
          <Button
            variant="secondary"
            className="full-width"
            icon={<LinkIcon size={16} />}
            onClick={() => navigate('/devices')}
          >
            Manage Pairing
          </Button>
        </GlassCard>

        <GlassCard className="action-card">
          <div className="card-header">
            <h3>Quick Actions</h3>
          </div>
          <div className="action-buttons">
            <Button
              variant="primary"
              size="lg"
              className="full-width animate-glow"
              icon={<CloudUpload size={24} />}
              onClick={() => triggerHostA(false)}
            >
              Push Workspace (Host A)
            </Button>
            <Button
              variant="secondary"
              size="lg"
              className="full-width"
              icon={<Zap size={24} />}
              onClick={() => navigate('/constellations')}
            >
              Constellations
            </Button>
            <Button 
              variant="secondary" 
              size="lg" 
              className="full-width" 
              icon={<Power size={24} />}
              onClick={triggerRollback}
            >
              Reset to Standby
            </Button>
          </div>
        </GlassCard>

        <GlassCard className="history-card span-2">
          <div className="card-header">
            <h3>Recent Transfers</h3>
          </div>
          <div className="transfer-list">
            {sessions.length === 0 ? (
              <p className="no-data">No recent transfers.</p>
            ) : (
              sessions.map(sess => (
                <div className="transfer-item" key={sess.transfer_id}>
                  <div className="transfer-icon"><MonitorSmartphone size={20} /></div>
                  <div className="transfer-details">
                    <h4>Transfer {sess.transfer_id.substring(0, 8)}</h4>
                    <p>{new Date(sess.created_at || sess.initiated_at).toLocaleString()}</p>
                  </div>
                  <span className={`transfer-status ${sess.status}`}>
                    {sess.status === 'complete'  && <CheckCircle size={16} className="text-green-400 mr-1" />}
                    {sess.status === 'failed'    && <XCircle    size={16} className="text-red-400 mr-1"   />}
                    {sess.status === 'pending'   && <Clock      size={16} className="text-yellow-400 mr-1"/>}
                    {sess.status}
                  </span>
                </div>
              ))
            )}
          </div>
        </GlassCard>
      </div>

      <TutorialModal
        isOpen={showTutorial}
        onClose={() => {
          setShowTutorial(false);
          if (window.location.hash === '#tutorial') {
            window.history.replaceState(null, '', window.location.pathname);
          }
        }}
      />

      <SelectiveTransferModal
        isOpen={showChecklist}
        onClose={() => {
          setShowChecklist(false);
          if (window.location.hash === '#checklist') {
            window.history.replaceState(null, '', window.location.pathname);
          }
        }}
        onConfirmTransfer={(selectedItems) => {
          console.log('Beaming selected items:', selectedItems);
          navigate('/sessions');
        }}
      />
    </div>
  );
};