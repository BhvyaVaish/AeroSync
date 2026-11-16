import React, { useEffect, useState } from 'react';
import { toast } from 'react-hot-toast';
import { MonitorSmartphone, Laptop, Smartphone, Monitor, Plus, X, Trash2, Sparkles } from 'lucide-react';
import { GlassCard } from '../components/GlassCard';
import { Button } from '../components/Button';
import { api } from '../services/api';
import { useWebSocket } from '../services/websocket';
import './Devices.css';

export const Devices = () => {
  const { onlineDevices } = useWebSocket();
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showPairingModal, setShowPairingModal] = useState(false);
  const [pairingMode, setPairingMode] = useState('initiate'); // 'initiate' or 'complete'
  const [pairingCode, setPairingCode] = useState('');
  const [generatedCode, setGeneratedCode] = useState(null);
  const [selectedDevice, setSelectedDevice] = useState(null);

  const fetchDevices = async () => {
    try {
      const res = await api.devices.list();
      setDevices(res.devices || []);
    } catch (err) {
      toast.error('Failed to load devices');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDevices();
  }, []);

  const handleDelete = async (deviceId) => {
    if (!window.confirm('Are you sure you want to remove this device?')) return;
    try {
      await api.devices.delete(deviceId);
      toast.success('Device removed');
      fetchDevices();
    } catch (err) {
      toast.error('Failed to remove device');
    }
  };

  const handleInitiatePairing = async (deviceId) => {
    try {
      const res = await api.devices.initiatePairing(deviceId);
      setGeneratedCode(res.pairing_code);
      setPairingMode('initiate');
      setShowPairingModal(true);
    } catch (err) {
      toast.error('Failed to generate pairing code');
    }
  };

  const handleCompletePairing = async (e) => {
    e.preventDefault();
    if (!selectedDevice) {
      toast.error('Please select a device to pair with');
      return;
    }
    
    try {
      await api.devices.completePairing(pairingCode, selectedDevice);
      toast.success('Devices paired successfully!');
      setShowPairingModal(false);
      setPairingCode('');
      fetchDevices();
    } catch (err) {
      toast.error(err.message || 'Invalid or expired pairing code');
    }
  };

  if (loading) return <div className="loading">Loading devices...</div>;

  return (
    <div className="devices-container">
      <div className="page-header">
        <div>
          <h1>My Devices</h1>
          <p className="subtitle">Manage your registered devices and pairings</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Button 
            variant="secondary" 
            icon={<Sparkles size={18} />}
            onClick={() => window.location.href = '/constellations'}
          >
            Constellations (Max 5)
          </Button>
          <Button 
            variant="primary" 
            icon={<Plus size={20} />}
            onClick={() => {
              setPairingMode('complete');
              setShowPairingModal(true);
            }}
          >
            Pair Device
          </Button>
        </div>
      </div>

      <div className="devices-grid">
        {devices.map(device => {
          const isOnline = onlineDevices.has(device.device_id);
          
          return (
            <GlassCard key={device.device_id} className="device-card">
              <div className="device-card-header">
                <div className="device-icon-wrapper">
                  {device.platform === 'windows' ? <Monitor size={24} /> :
                   device.platform === 'mac' ? <Laptop size={24} /> :
                   <Smartphone size={24} />}
                </div>
                <div className="device-actions">
                  <button className="icon-btn delete-btn" onClick={() => handleDelete(device.device_id)}>
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
              
              <div className="device-info">
                <h3>{device.device_name}</h3>
                <div className="device-status">
                  <span className={`status-dot ${isOnline ? 'online' : 'offline'}`}></span>
                  <span>{isOnline ? 'Online' : 'Offline'}</span>
                </div>
                <p className="device-meta">ID: {device.device_id.substring(0, 8)}</p>
              </div>

              <div className="device-footer">
                <Button 
                  variant="secondary" 
                  className="full-width"
                  onClick={() => handleInitiatePairing(device.device_id)}
                >
                  Generate Pairing Code
                </Button>
              </div>
            </GlassCard>
          );
        })}
      </div>

      {showPairingModal && (
        <div className="modal-overlay">
          <GlassCard className="modal-content">
            <div className="modal-header">
              <h2>{pairingMode === 'initiate' ? 'Pairing Code' : 'Enter Pairing Code'}</h2>
              <button className="close-btn" onClick={() => setShowPairingModal(false)}>
                <X size={24} />
              </button>
            </div>
            
            <div className="modal-body">
              {pairingMode === 'initiate' ? (
                <div className="code-display">
                  <p>Enter this code on your other device to pair them:</p>
                  <div className="big-code">{generatedCode}</div>
                  <p className="code-timer">Expires in 15 minutes</p>
                </div>
              ) : (
                <form onSubmit={handleCompletePairing}>
                  <div className="form-group">
                    <label>Target Device (Your current device)</label>
                    <select 
                      value={selectedDevice || ''} 
                      onChange={(e) => setSelectedDevice(e.target.value)}
                      required
                      className="device-select"
                    >
                      <option value="">Select a device...</option>
                      {devices.map(d => (
                        <option key={d.device_id} value={d.device_id}>{d.device_name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>6-Digit Code</label>
                    <input 
                      type="text" 
                      placeholder="123456" 
                      maxLength="6"
                      required
                      value={pairingCode}
                      onChange={(e) => setPairingCode(e.target.value.toUpperCase())}
                      className="code-input"
                    />
                  </div>
                  <Button type="submit" variant="primary" className="full-width mt-4">
                    Complete Pairing
                  </Button>
                </form>
              )}
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
};
