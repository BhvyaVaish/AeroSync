import { Globe, AppWindow, Clipboard, Cpu } from 'lucide-react';
import './QueueMonitorWidget.css';

export const QueueMonitorWidget = ({ queueData }) => {
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
          <span className="queue-pulse-dot" />
          <h3>Active Workspace</h3>
        </div>
      </div>

      <div className="queue-orbital-display">
        {/* Precision Concentric Telemetry Radar */}
        <div className="orbital-ring-container">
          <div className="orbital-ring" />
          <div className="orbital-ring-inner" />
          <div className="orbital-count-node">
            <span className="orbital-count-number">{data.size}</span>
            <span className="orbital-count-label">Total Items</span>
          </div>
        </div>

        {/* Minimalist Breakdown Badges — Subtle Frosted Glass & Silver */}
        <div className="queue-breakdown-grid">
          <div className="breakdown-badge">
            <div className="breakdown-info">
              <AppWindow size={15} className="breakdown-icon" />
              <span>Windows</span>
            </div>
            <span className="breakdown-val">{data.windows}</span>
          </div>

          <div className="breakdown-badge">
            <div className="breakdown-info">
              <Globe size={15} className="breakdown-icon" />
              <span>Browser Tabs</span>
            </div>
            <span className="breakdown-val">{data.tabs}</span>
          </div>

          <div className="breakdown-badge">
            <div className="breakdown-info">
              <Clipboard size={15} className="breakdown-icon" />
              <span>Clipboard</span>
            </div>
            <span className="breakdown-val">{data.clipboard}</span>
          </div>

          <div className="breakdown-badge">
            <div className="breakdown-info">
              <Cpu size={15} className="breakdown-icon" />
              <span>Processes</span>
            </div>
            <span className="breakdown-val">{data.processes}</span>
          </div>
        </div>
      </div>

      {/* Capacity Progress */}
      <div className="queue-capacity-bar">
        <div className="capacity-labels">
          <span>Capacity: {data.size} / {data.capacity || 500} items</span>
        </div>
        <div className="capacity-track">
          <div className="capacity-fill" style={{ width: `${Math.max(4, percentage)}%` }} />
        </div>
      </div>
    </div>
  );
};
