import React, { useState } from 'react';
import { X, CheckSquare, Square, Rocket, Check, Layers, Globe, AppWindow, Clipboard } from 'lucide-react';
import { Button } from './Button';
import './SelectiveTransferModal.css';

export const SelectiveTransferModal = ({ isOpen, onClose, onConfirmTransfer, initialData }) => {
  if (!isOpen) return null;

  // Sample or incoming items
  const [selectedWindows, setSelectedWindows] = useState({
    win1: true,
    win2: true,
    win3: true,
  });

  const [selectedTabs, setSelectedTabs] = useState({
    tab1: true,
    tab2: true,
  });

  const [includeClipboard, setIncludeClipboard] = useState(true);
  const [relaunchApps, setRelaunchApps] = useState(true);

  const toggleWindow = (key) => {
    setSelectedWindows((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const toggleTab = (key) => {
    setSelectedTabs((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleBeamSelected = () => {
    if (onConfirmTransfer) {
      onConfirmTransfer({
        windows: selectedWindows,
        tabs: selectedTabs,
        clipboard: includeClipboard,
        relaunch: relaunchApps,
      });
    }
    onClose();
  };

  const handleBeamAll = () => {
    if (onConfirmTransfer) {
      onConfirmTransfer({ all: true });
    }
    onClose();
  };

  return (
    <div className="checklist-overlay" onClick={onClose}>
      <div className="checklist-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="checklist-header">
          <div className="checklist-title-area">
            <h2>
              <Layers size={20} style={{ display: 'inline-block', verticalAlign: 'middle', marginRight: 8, color: '#38BDF8' }} />
              Selective Workspace Beam (Host A)
            </h2>
            <p className="checklist-subtitle">
              Long Fist Detected (≥2.0s). Choose exactly which elements to beam to your Constellation:
            </p>
          </div>
          <button className="tutorial-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="checklist-body">
          {/* Windows Section */}
          <div className="checklist-section">
            <div className="checklist-section-header">
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <AppWindow size={16} /> Open Application Windows
              </span>
            </div>
            <div className="checklist-items-list">
              <div
                className={`checklist-item-row ${selectedWindows.win1 ? 'selected' : ''}`}
                onClick={() => toggleWindow('win1')}
              >
                <input type="checkbox" checked={selectedWindows.win1} readOnly className="checklist-checkbox" />
                <div className="checklist-item-text">
                  <span className="checklist-item-primary">Visual Studio Code — AeroSync</span>
                  <span className="checklist-item-secondary">Code.exe • Top-Left Quadrant • 1080x720</span>
                </div>
              </div>

              <div
                className={`checklist-item-row ${selectedWindows.win2 ? 'selected' : ''}`}
                onClick={() => toggleWindow('win2')}
              >
                <input type="checkbox" checked={selectedWindows.win2} readOnly className="checklist-checkbox" />
                <div className="checklist-item-text">
                  <span className="checklist-item-primary">Windows Terminal — PowerShell</span>
                  <span className="checklist-item-secondary">WindowsTerminal.exe • Bottom-Left Quadrant</span>
                </div>
              </div>

              <div
                className={`checklist-item-row ${selectedWindows.win3 ? 'selected' : ''}`}
                onClick={() => toggleWindow('win3')}
              >
                <input type="checkbox" checked={selectedWindows.win3} readOnly className="checklist-checkbox" />
                <div className="checklist-item-text">
                  <span className="checklist-item-primary">Notepad — MeetingNotes.txt</span>
                  <span className="checklist-item-secondary">Notepad.exe • WM_GETTEXT Captured</span>
                </div>
              </div>
            </div>
          </div>

          {/* Browser Tabs Section */}
          <div className="checklist-section">
            <div className="checklist-section-header">
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Globe size={16} /> Browser Tabs (Chrome Auto-Launch)
              </span>
            </div>
            <div className="checklist-items-list">
              <div
                className={`checklist-item-row ${selectedTabs.tab1 ? 'selected' : ''}`}
                onClick={() => toggleTab('tab1')}
              >
                <input type="checkbox" checked={selectedTabs.tab1} readOnly className="checklist-checkbox" />
                <div className="checklist-item-text">
                  <span className="checklist-item-primary">GitHub — AeroSync Repository</span>
                  <span className="checklist-item-secondary">https://github.com/aerosync/core</span>
                </div>
              </div>

              <div
                className={`checklist-item-row ${selectedTabs.tab2 ? 'selected' : ''}`}
                onClick={() => toggleTab('tab2')}
              >
                <input type="checkbox" checked={selectedTabs.tab2} readOnly className="checklist-checkbox" />
                <div className="checklist-item-text">
                  <span className="checklist-item-primary">Python 3.14 Documentation</span>
                  <span className="checklist-item-secondary">https://docs.python.org/3/</span>
                </div>
              </div>
            </div>
          </div>

          {/* Options Section */}
          <div className="checklist-section">
            <div className="checklist-section-header">Options & Clipboard</div>
            <div className="checklist-items-list">
              <div
                className={`checklist-item-row ${includeClipboard ? 'selected' : ''}`}
                onClick={() => setIncludeClipboard(!includeClipboard)}
              >
                <input type="checkbox" checked={includeClipboard} readOnly className="checklist-checkbox" />
                <div className="checklist-item-text">
                  <span className="checklist-item-primary">Restore Clipboard Text</span>
                  <span className="checklist-item-secondary">Current clipboard buffer (plain text)</span>
                </div>
              </div>

              <div
                className={`checklist-item-row ${relaunchApps ? 'selected' : ''}`}
                onClick={() => setRelaunchApps(!relaunchApps)}
              >
                <input type="checkbox" checked={relaunchApps} readOnly className="checklist-checkbox" />
                <div className="checklist-item-text">
                  <span className="checklist-item-primary">Auto-Relaunch Missing Applications</span>
                  <span className="checklist-item-secondary">Attempt to launch application binaries on Target B</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="checklist-footer">
          <Button variant="secondary" size="md" onClick={handleBeamAll}>
            Beam Everything (Full)
          </Button>
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <Button variant="secondary" size="md" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="md"
              icon={<Rocket size={16} />}
              onClick={handleBeamSelected}
            >
              Beam Selected
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
