import React, { useEffect, useState } from 'react';
import { toast } from 'react-hot-toast';
import { Sparkles, Plus, Key, Copy, Check, Monitor, Trash2, Users, Shield, LogOut, X } from 'lucide-react';
import { GlassCard } from '../components/GlassCard';
import { Button } from '../components/Button';
import { api } from '../services/api';
import { useWebSocket } from '../services/websocket';
import './Constellations.css';

export const Constellations = () => {
  const { onlineDevices } = useWebSocket();
  const [constellations, setConstellations] = useState([]);
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showJoinModal, setShowJoinModal] = useState(false);

  // Form states
  const [createName, setCreateName] = useState('');
  const [createDeviceId, setCreateDeviceId] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [joinDeviceId, setJoinDeviceId] = useState('');
  const [copiedCode, setCopiedCode] = useState(null);

  const fetchData = async () => {
    try {
      const [cRes, dRes] = await Promise.all([
        api.constellations.list(),
        api.devices.list()
      ]);
      setConstellations(cRes.constellations || []);
      setDevices(dRes.devices || []);
      if (dRes.devices?.length > 0) {
        setCreateDeviceId(dRes.devices[0].device_id);
        setJoinDeviceId(dRes.devices[0].device_id);
      }
    } catch (err) {
      toast.error('Failed to load constellations or devices');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCopyCode = (code) => {
    navigator.clipboard.writeText(code);
    setCopiedCode(code);
    toast.success('Join code copied to clipboard!');
    setTimeout(() => setCopiedCode(null), 2500);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!createName.trim()) {
      toast.error('Please enter a constellation name');
      return;
    }
    try {
      const res = await api.constellations.create(createName.trim(), createDeviceId || null);
      toast.success(`Constellation "${res.name}" created! Join code: ${res.join_code}`);
      setShowCreateModal(false);
      setCreateName('');
      fetchData();
    } catch (err) {
      toast.error(err.message || 'Failed to create constellation');
    }
  };

  const handleJoin = async (e) => {
    e.preventDefault();
    if (!joinCode.trim()) {
      toast.error('Please enter a constellation join code');
      return;
    }
    if (!joinDeviceId) {
      toast.error('Please select which computer to link');
      return;
    }
    try {
      const res = await api.constellations.join(joinCode.trim().toUpperCase(), joinDeviceId);
      toast.success(`Linked to constellation "${res.name}"!`);
      setShowJoinModal(false);
      setJoinCode('');
      fetchData();
    } catch (err) {
      toast.error(err.message || 'Failed to join constellation');
    }
  };

  const handleLeave = async (constellationId, deviceId, constellationName) => {
    if (!window.confirm(`Remove this computer from "${constellationName}"?`)) return;
    try {
      await api.constellations.leave(constellationId, deviceId);
      toast.success('Left constellation');
      fetchData();
    } catch (err) {
      toast.error(err.message || 'Failed to leave constellation');
    }
  };

  const handleDeleteConstellation = async (constellationId, constellationName) => {
    if (!window.confirm(`Are you sure you want to delete constellation "${constellationName}"? This will unlink all computers.`)) {
      return;
    }
    try {
      await api.constellations.delete(constellationId);
      toast.success(`Constellation "${constellationName}" deleted`);
      fetchData();
    } catch (err) {
      toast.error(err.message || 'Failed to delete constellation');
    }
  };

  if (loading) return <div className="loading">Loading Constellations...</div>;

  return (
    <div className="constellations-container">
      {/* Page Header */}
      <div className="page-header">
        <div>
          <div className="title-with-badge">
            <h1>Constellations</h1>
            <span className="constellation-limit-pill">Max 5 Computers</span>
          </div>
          <p className="subtitle">
            Isolated rooms of linked computers. Any computer can join using the unique code.
          </p>
        </div>
        <div className="header-actions">
          <Button 
            variant="primary" 
            icon={<Key size={18} />}
            onClick={() => setShowJoinModal(true)}
          >
            Join Constellation
          </Button>
          <Button 
            variant="primary" 
            icon={<Plus size={18} />}
            onClick={() => setShowCreateModal(true)}
          >
            Create Constellation
          </Button>
        </div>
      </div>

      {/* Empty State */}
      {constellations.length === 0 ? (
        <GlassCard className="empty-constellation-card">
          <div className="empty-icon-wrap">
            <Sparkles size={40} className="glow-icon" />
          </div>
          <h2>No Constellations Yet</h2>
          <p>
            Create an isolated room for up to 5 computers, or join an existing constellation with a code to instantly link your devices together.
          </p>
          <div className="empty-actions">
            <Button variant="primary" onClick={() => setShowCreateModal(true)}>
              Create First Constellation
            </Button>
            <Button variant="secondary" onClick={() => setShowJoinModal(true)}>
              Join with Code
            </Button>
          </div>
        </GlassCard>
      ) : (
        <div className="constellations-grid">
          {constellations.map(c => {
            const isFull = c.device_count >= c.max_devices;
            const progressPercent = Math.min(100, (c.device_count / c.max_devices) * 100);

            return (
              <GlassCard key={c.id} className="constellation-card">
                {/* Header */}
                <div className="c-card-header">
                  <div className="c-title-group">
                    <div className="c-icon">
                      <Sparkles size={20} />
                    </div>
                    <div>
                      <h3>{c.name}</h3>
                      <span className="c-date">
                        Created {c.created_at ? new Date(c.created_at).toLocaleDateString() : 'recently'}
                      </span>
                    </div>
                  </div>
                  <div className="c-header-right">
                    <span className={`c-capacity-badge ${isFull ? 'full' : 'available'}`}>
                      {isFull ? 'Full (5/5)' : `${c.device_count} / ${c.max_devices} Computers`}
                    </span>
                    <button
                      className="icon-btn delete-btn"
                      onClick={() => handleDeleteConstellation(c.id, c.name)}
                      title="Delete Constellation"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>

                {/* Join Code Box */}
                <div className="join-code-banner">
                  <div className="code-text-group">
                    <span className="code-label">ROOM JOIN CODE</span>
                    <span className="code-value">{c.join_code}</span>
                  </div>
                  <button 
                    className="copy-code-btn"
                    onClick={() => handleCopyCode(c.join_code)}
                    title="Copy unique code"
                  >
                    {copiedCode === c.join_code ? <Check size={18} className="text-green" /> : <Copy size={18} />}
                    <span>{copiedCode === c.join_code ? 'Copied' : 'Copy'}</span>
                  </button>
                </div>

                {/* Capacity Progress Bar */}
                <div className="capacity-bar-wrap">
                  <div className="capacity-bar-label">
                    <span>Linked Computers</span>
                    <span>{c.device_count} of 5 max</span>
                  </div>
                  <div className="capacity-progress-track">
                    <div 
                      className={`capacity-progress-fill ${isFull ? 'full' : ''}`}
                      style={{ width: `${progressPercent}%` }}
                    />
                  </div>
                </div>

                {/* Member Computers List */}
                <div className="c-members-section">
                  <span className="section-title">
                    <Users size={14} /> Linked Computers in this Room:
                  </span>
                  <div className="c-members-list">
                    {c.members.map(m => {
                      const isOnline = onlineDevices.has(m.device_id);
                      return (
                        <div key={m.device_id} className="c-member-item">
                          <div className="member-main">
                            <span className={`status-dot ${isOnline ? 'online' : 'offline'}`} />
                            <Monitor size={16} className="member-icon" />
                            <span className="member-name">{m.device_name}</span>
                            {m.role === 'owner' && <span className="owner-tag">Creator</span>}
                          </div>
                          <div className="member-actions">
                            <button 
                              className="leave-btn"
                              title="Leave constellation"
                              onClick={() => handleLeave(c.id, m.device_id, c.name)}
                            >
                              <LogOut size={14} />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </GlassCard>
            );
          })}
        </div>
      )}

      {/* Modal: Create Constellation */}
      {showCreateModal && (
        <div className="modal-overlay">
          <GlassCard className="modal-content">
            <div className="modal-header">
              <h2>Create New Constellation</h2>
              <button className="close-btn" onClick={() => setShowCreateModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleCreate} className="modal-body">
              <p className="modal-desc">
                A constellation is an isolated room that links up to <strong>5 computers</strong> together. 
                You'll receive a unique join code to share.
              </p>
              <div className="form-group">
                <label>Constellation Name</label>
                <input 
                  type="text" 
                  placeholder="e.g. Work Studio, Office Pod, Testing Room" 
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  required
                  autoFocus
                  className="c-input"
                />
              </div>
              <div className="form-group">
                <label>Select Initial Computer (Optional)</label>
                <select 
                  value={createDeviceId}
                  onChange={(e) => setCreateDeviceId(e.target.value)}
                  className="c-select"
                >
                  <option value="">Do not link a computer yet</option>
                  {devices.map(d => (
                    <option key={d.device_id} value={d.device_id}>
                      {d.device_name} ({d.platform})
                    </option>
                  ))}
                </select>
              </div>
              <Button type="submit" variant="primary" className="full-width mt-4">
                Create Constellation Room
              </Button>
            </form>
          </GlassCard>
        </div>
      )}

      {/* Modal: Join Constellation */}
      {showJoinModal && (
        <div className="modal-overlay">
          <GlassCard className="modal-content">
            <div className="modal-header">
              <h2>Join Constellation Room</h2>
              <button className="close-btn" onClick={() => setShowJoinModal(false)}>
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleJoin} className="modal-body">
              <p className="modal-desc">
                Enter the unique code of the constellation room you want this computer to join.
                Each constellation holds a maximum of <strong>5 computers</strong>.
              </p>
              <div className="form-group">
                <label>Unique Constellation Code</label>
                <input 
                  type="text" 
                  placeholder="e.g. CST-7X9K2" 
                  value={joinCode}
                  onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
                  required
                  autoFocus
                  className="c-input uppercase"
                />
              </div>
              <div className="form-group">
                <label>Computer to Link</label>
                <select 
                  value={joinDeviceId}
                  onChange={(e) => setJoinDeviceId(e.target.value)}
                  required
                  className="c-select"
                >
                  <option value="">Select a computer...</option>
                  {devices.map(d => (
                    <option key={d.device_id} value={d.device_id}>
                      {d.device_name} ({d.platform})
                    </option>
                  ))}
                </select>
              </div>
              <Button type="submit" variant="primary" className="full-width mt-4">
                Link to Constellation
              </Button>
            </form>
          </GlassCard>
        </div>
      )}
    </div>
  );
};
