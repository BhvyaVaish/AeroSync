import React from 'react';
import { Layers, Globe, AppWindow, Clipboard, Cpu, Activity } from 'lucide-react';
import './QueueMonitorWidget.css';

export const QueueMonitorWidget = ({ queueData }) => {
  // Mock fallback or live queue data
  const data = queueData || {
    size: 14,
    capacity: 500,
    windows: 5,
    tabs: 6,
    clipboard: 1,
    processes: 2,
    mode: 'FIFO Chronological',
  };

  const percentage = Math.min(100, Math.round((data.size / (data.capacity || 500)) * 100));

  return (
    <div className="queue-monitor-card glass-panel">
      <div className="queue-monitor-header">
        <div className="queue-telemetry-title">
          <span className="queue-pulse-dot"></span>
          <h3>Orbital Memory Deque</h3>
        </div>
        <span style={{ fontSize: '0.75rem', color: '#00f5d4', background: 'rgba(0, 245, 212, 0.1)', padding: '0.2rem 0.5rem', borderRadius: 6 }}>
          FIFO Live Stack
        </span>
      </div>

      <div className="queue-orbital-display">
        {/* Animated Celestial Orbital Ring */}
        <div className="orbital-ring-container">
          <div className="orbital-ring"></div>
          <div className="orbital-ring-inner"></div>
          <div className="orbital-count-node">
            <span className="orbital-count-number">{data.size}</span>
            <span className="orbital-count-label">Nodes Enqueued</span>
          </div>
        </div>

        {/* Telemetry Breakdown Badges */}
        <div className="queue-breakdown-grid">
          <div className="breakdown-badge">
            <div className="breakdown-info">
              <AppWindow size={15} color="#38bdf8" />
              <span>Windows</span>
            </div>
            <span className="breakdown-val">{data.windows}</span>
          </div>

          <div className="breakdown-badge">
            <div className="breakdown-info">
              <Globe size={15} color="#00f5d4" />
              <span>Browser Tabs</span>
            </div>
            <span className="breakdown-val">{data.tabs}</span>
          </div>

          <div className="breakdown-badge">
            <div className="breakdown-info">
              <Clipboard size={15} color="#fbbf24" />
              <span>Clipboard</span>
            </div>
            <span className="breakdown-val">{data.clipboard}</span>
          </div>

          <div className="breakdown-badge">
            <div className="breakdown-info">
              <Cpu size={15} color="#a855f7" />
              <span>Processes</span>
            </div>
            <span className="breakdown-val">{data.processes}</span>
          </div>
        </div>
      </div>

      {/* Capacity & Telemetry Progress */}
      <div className="queue-capacity-bar">
        <div className="capacity-labels">
          <span>Capacity: {data.size} / {data.capacity || 500} entries</span>
          <span>Order: Oldest → Newest (FIFO)</span>
        </div>
        <div className="capacity-track">
          <div className="capacity-fill" style={{ width: `${Math.max(4, percentage)}%` }}></div>
        </div>
      </div>
    </div>
  );
};
