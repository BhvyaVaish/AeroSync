import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';

import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { Devices } from './pages/Devices';
import { Sessions } from './pages/Sessions';
import { Constellations } from './pages/Constellations';
import { Navbar } from './components/Navbar';
import { CameraWidget } from './components/CameraWidget';
import { WebSocketProvider } from './services/websocket';
import { auth } from './services/auth';
import { api } from './services/api';
import './App.css';

const ProtectedRoute = ({ children }) => {
  if (!auth.isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (auth.isAuthenticated()) {
      api.auth.me()
        .then(data => setUser(data))
        .catch(() => auth.clearTokens())
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  if (loading) {
    return <div className="app-loading">Loading AeroSync...</div>;
  }

  return (
    <WebSocketProvider>
      <BrowserRouter>
        <div className="app-container">
          <Toaster position="top-right" toastOptions={{
            style: {
              background: 'var(--bg-surface)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-light)',
            }
          }} />
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={
              <ProtectedRoute>
                <>
                  <Navbar user={user} />
                  <main className="main-content">
                    <Dashboard />
                  </main>
                </>
              </ProtectedRoute>
            } />
            <Route path="/constellations" element={
              <ProtectedRoute>
                <>
                  <Navbar user={user} />
                  <main className="main-content">
                    <Constellations />
                  </main>
                </>
              </ProtectedRoute>
            } />
            <Route path="/devices" element={
              <ProtectedRoute>
                <>
                  <Navbar user={user} />
                  <main className="main-content">
                    <Devices />
                  </main>
                </>
              </ProtectedRoute>
            } />
            <Route path="/sessions" element={
              <ProtectedRoute>
                <>
                  <Navbar user={user} />
                  <main className="main-content">
                    <Sessions />
                  </main>
                </>
              </ProtectedRoute>
            } />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          {user && <CameraWidget />}
        </div>
      </BrowserRouter>
    </WebSocketProvider>
  );
}

export default App;
