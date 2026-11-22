import { NavLink, useNavigate } from 'react-router-dom';
import { MonitorSmartphone, CloudUpload, Sparkles, LogOut } from 'lucide-react';
import { auth } from '../services/auth';
import './Navbar.css';

export const Navbar = ({ user }) => {
  const navigate = useNavigate();

  const handleLogout = () => {
    auth.clearTokens();
    window.location.href = '/login';
  };

  return (
    <nav className="navbar-wrapper">
      <div className="navbar glass-panel">
        <div className="navbar-brand" onClick={() => navigate('/')}>
          <span className="brand-dot" />
          <span className="logo-text">AeroSync</span>
        </div>

        <div className="navbar-menu">
          <NavLink to="/" end className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span>Overview</span>
          </NavLink>
          <NavLink to="/constellations" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Sparkles size={14} />
            <span>Constellations</span>
          </NavLink>
          <NavLink to="/devices" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <MonitorSmartphone size={14} />
            <span>Devices</span>
          </NavLink>
          <NavLink to="/sessions" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <CloudUpload size={14} />
            <span>Sessions</span>
          </NavLink>
        </div>

        <div className="navbar-actions">
          {user && <span className="user-name">{user.display_name}</span>}
          <button className="user-profile-btn" onClick={handleLogout} title="Logout">
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </nav>
  );
};
