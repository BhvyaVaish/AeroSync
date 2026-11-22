import React from 'react';
import { ArrowUpRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import './Footer.css';

export const Footer = () => {
  const navigate = useNavigate();

  return (
    <footer className="app-footer">
      <div className="footer-container">
        {/* Top Grid */}
        <div className="footer-grid">
          {/* Brand Column */}
          <div className="footer-col footer-brand-col">
            <div className="footer-brand" onClick={() => navigate('/')}>
              <span className="footer-brand-dot" />
              <span className="footer-logo-text">AeroSync</span>
            </div>
            <p className="footer-tagline">
              Seamless cross-device workspace synchronization. Connect, control, and move your work fluidly across multiple screens.
            </p>
          </div>

          {/* Navigation Links */}
          <div className="footer-col">
            <h4 className="footer-heading">NAVIGATION</h4>
            <ul className="footer-links">
              <li><button onClick={() => navigate('/')} className="footer-link-btn">Overview</button></li>
              <li><button onClick={() => navigate('/constellations')} className="footer-link-btn">Constellations</button></li>
              <li><button onClick={() => navigate('/devices')} className="footer-link-btn">Devices</button></li>
              <li><button onClick={() => navigate('/sessions')} className="footer-link-btn">Sessions</button></li>
            </ul>
          </div>

          {/* Resources */}
          <div className="footer-col">
            <h4 className="footer-heading">RESOURCES</h4>
            <ul className="footer-links">
              <li><button onClick={() => navigate('/#tutorial')} className="footer-link-btn">Walkthrough Guide</button></li>
              <li><span className="footer-static-item">Privacy Policy</span></li>
              <li><span className="footer-static-item">Documentation</span></li>
              <li><span className="footer-static-item">System Status</span></li>
            </ul>
          </div>
        </div>

        {/* Divider */}
        <div className="footer-divider" />

        {/* Bottom Bar with Formal Author Attribution */}
        <div className="footer-bottom-bar">
          <div className="footer-copyright">
            © {new Date().getFullYear()} AeroSync. All rights reserved.
          </div>

          {/* Formal Developer Attribution to Bhvya Vaish */}
          <div className="footer-developer">
            <span className="dev-prefix">Developed by</span>
            <a
              href="https://www.linkedin.com/in/bhvya-vaish"
              target="_blank"
              rel="noopener noreferrer"
              className="dev-link-pill"
              title="Bhvya Vaish on LinkedIn"
            >
              <svg className="linkedin-svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/>
              </svg>
              <span className="dev-name">Bhvya Vaish</span>
              <ArrowUpRight size={13} className="ext-icon" />
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
};
