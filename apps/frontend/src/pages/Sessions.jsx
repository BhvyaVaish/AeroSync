import React, { useEffect, useState } from 'react';
import { toast } from 'react-hot-toast';
import { RefreshCw, MonitorSmartphone, CheckCircle, XCircle, Clock, Trash2 } from 'lucide-react';
import { GlassCard } from '../components/GlassCard';
import { Button } from '../components/Button';
import { api } from '../services/api';
import './Sessions.css';

export const Sessions = () => {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchSessions = async () => {
    setLoading(true);
    try {
      const res = await api.sessions.history(50);
      setSessions(res.sessions || []);
    } catch (err) {
      toast.error('Failed to load session history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const handleCancel = async (transferId) => {
    if (!window.confirm('Cancel this pending transfer?')) return;
    try {
      await api.sessions.cancel(transferId);
      toast.success('Transfer cancelled');
      fetchSessions();
    } catch (err) {
      toast.error('Failed to cancel transfer');
    }
  };

  const formatSize = (bytes) => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className="sessions-container">
      <div className="page-header">
        <div>
          <h1>Transfer History</h1>
          <p className="subtitle">View all your workspace transfers across devices</p>
        </div>
        <Button 
          variant="secondary" 
          icon={<RefreshCw size={16} className={loading ? 'animate-spin' : ''} />}
          onClick={fetchSessions}
        >
          Refresh
        </Button>
      </div>

      <GlassCard className="sessions-card">
        {loading && sessions.length === 0 ? (
          <div className="loading-state">Loading history...</div>
        ) : sessions.length === 0 ? (
          <div className="empty-state">No transfers found.</div>
        ) : (
          <div className="table-responsive">
            <table className="sessions-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Date</th>
                  <th>Source</th>
                  <th>Target</th>
                  <th>Size</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map(sess => (
                  <tr key={sess.transfer_id}>
                    <td className="font-mono text-sm">{sess.transfer_id ? sess.transfer_id.substring(0, 8) : ''}</td>
                    <td>{(sess.initiated_at || sess.created_at) ? new Date(sess.initiated_at || sess.created_at).toLocaleString() : '-'}</td>
                    <td>{sess.source_device_name || (sess.source_device_id ? sess.source_device_id.substring(0, 8) : '-')}</td>
                    <td>{sess.target_device_name || (sess.target_device_id ? sess.target_device_id.substring(0, 8) : '-')}</td>
                    <td>{formatSize(sess.package_size_bytes)}</td>
                    <td>
                      <span className={`status-badge ${sess.status}`}>
                        {(sess.status === 'completed' || sess.status === 'complete') && <CheckCircle size={14} />}
                        {sess.status === 'failed' && <XCircle size={14} />}
                        {sess.status === 'pending' && <Clock size={14} />}
                        {sess.status}
                      </span>
                    </td>
                    <td>
                      {sess.status === 'pending' && (
                        <button 
                          className="icon-btn text-red"
                          onClick={() => handleCancel(sess.transfer_id)}
                          title="Cancel Transfer"
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassCard>
    </div>
  );
};
