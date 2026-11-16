import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GlassCard } from '../components/GlassCard';
import { Button } from '../components/Button';
import { TutorialModal } from '../components/TutorialModal';
import { QueueMonitorWidget } from '../components/QueueMonitorWidget';
import { SelectiveTransferModal } from '../components/SelectiveTransferModal';
import {
  MonitorSmartphone, CloudUpload, Link as LinkIcon, Power,
  CheckCircle, XCircle, Clock, Zap, Radio, BookOpen, CheckSquare
} from 'lucide-react';
import { api } from '../services/api';
import { useWebSocket } from '../services/websocket';
import './Dashboard.css';

// Role state display config (mirrors shared/constants.py RoleState)
const ROLE_CONFIG = {
  neutral:      { label: 'NEUTRAL',                  color: '#888',    icon: '○',  tip: 'Make a FIST to become Host A' },
  host:         { label: 'HOST A — Capturing',        color: '#f97316', icon: '✊',  tip: 'Workspace is being captured…' },
  candidate:    { label: 'CANDIDATE — Throw to Claim',color: '#06b6d4', icon: '◎',  tip: 'Make a THROW gesture to claim Target B' },
  target:       { label: 'TARGET B — Receiving',      color: '#a855f7', icon: '🚀', tip: 'Workspace arriving…' },
  transferring: { label: 'TRANSFERRING…',             color: '#22c55e', icon: '⇄',  tip: 'Data in transit' },
};

export const Dashboard = () => {
  const navigate = useNavigate();
  const { onlineDevices, connectionStatus, connect, lastMessage } = useWebSocket();
  const [devices, setDevices] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [roleState, setRoleState] = useState('neutral');
  const [hostPeer, setHostPeer] = useState(null);   // which peer is currently Host A
  const [showTutorial, setShowTutorial] = useState(window.location.hash === '#tutorial');
  const [showChecklist, setShowChecklist] = useState(window.location.hash === '#checklist');

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

  const activeDevice = devices.length > 0 ? devices[0] : null;
  const role = ROLE_CONFIG[roleState] || ROLE_CONFIG.neutral;

  return (
    <div className="dashboard-container">
      <div className="dashboard-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>Workspace Overview</h1>
          <p className="subtitle">Manage your paired devices and active sessions</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Button
            variant="secondary"
            size="md"
            icon={<CheckSquare size={18} color="#f97316" />}
            onClick={() => setShowChecklist(true)}
            style={{ borderColor: 'rgba(249, 115, 22, 0.4)', color: '#f97316' }}
          >
            Selective Beam (Long Fist 📋)
          </Button>
          <Button
            variant="secondary"
            size="md"
            icon={<BookOpen size={18} color="#00f5d4" />}
            onClick={() => setShowTutorial(true)}
            style={{ borderColor: 'rgba(0, 245, 212, 0.4)', color: '#00f5d4' }}
          >
            Walkthrough Guide
          </Button>
        </div>
      </div>

      {/* ── Role Status Banner ───────────────────────────────────────────── */}
      <div
        className="role-banner"
        style={{ borderLeft: `4px solid ${role.color}` }}
      >
        <span className="role-icon" style={{ color: role.color }}>{role.icon}</span>
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
            <h3>Active Device</h3>
            <span className={`status-indicator ${connectionStatus === 'connected' ? 'online' : 'offline'}`}></span>
          </div>
          <div className="device-info">
            <MonitorSmartphone size={48} className="device-icon" />
            <div>
              <h2>{activeDevice ? activeDevice.device_name : 'No Devices'}</h2>
              <p>{activeDevice ? activeDevice.platform : ''} • {connectionStatus === 'connected' ? 'Connected' : 'Offline'}</p>
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
              onClick={() => navigate('/sessions')}
              disabled={devices.length < 2}
            >
              Push Workspace
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
            <Button variant="secondary" size="lg" className="full-width" icon={<Power size={24} />}>
              Disconnect
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
