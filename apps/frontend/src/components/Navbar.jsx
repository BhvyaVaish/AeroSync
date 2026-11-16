import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { MonitorSmartphone, CloudUpload, Sparkles, UserCircle, LogOut } from 'lucide-react';
import { auth } from '../services/auth';
import './Navbar.css';

export const Navbar = ({ user }) => {
  const navigate = useNavigate();

  const handleLogout = () => {
    auth.clearTokens();
    window.location.href = '/login';
  };

  return (
    <nav className="navbar glass-panel">
      <div className="navbar-brand" onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>
        <span className="logo-icon">▲</span>
        <span className="logo-text">AeroSync</span>
      </div>
      
      <div className="navbar-menu">
        <NavLink to="/constellations" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <Sparkles size={20} />
          <span>Constellations</span>
        </NavLink>
        <NavLink to="/devices" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <MonitorSmartphone size={20} />
          <span>Devices</span>
        </NavLink>
        <NavLink to="/sessions" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <CloudUpload size={20} />
          <span>Sessions</span>
        </NavLink>
      </div>

      <div className="navbar-actions">
        {user && <span className="user-name">{user.display_name}</span>}
        <button className="user-profile-btn" onClick={handleLogout} title="Logout">
          <LogOut size={20} />
        </button>
      </div>
    </nav>
  );
};
