import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';

import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { Devices } from './pages/Devices';
import { Sessions } from './pages/Sessions';
import { Constellations } from './pages/Constellations';
import { Navbar } from './components/Navbar';
import { Footer } from './components/Footer';
import { CameraWidget } from './components/CameraWidget';
import { SpaceBackground } from './components/SpaceBackground';
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
    return (
      <>
        <SpaceBackground />
        <div className="app-loading">Initialising AeroSync</div>
      </>
    );
  }

  return (
    <WebSocketProvider>
      <BrowserRouter>
        {/* Deep space animated canvas behind everything */}
        <SpaceBackground />

        <div className="app-container">
          <Toaster
            position="top-right"
            toastOptions={{
              style: {
                background: 'rgba(6, 10, 18, 0.95)',
                color: '#F0F4F8',
                border: '1px solid rgba(255,255,255,0.10)',
                borderRadius: '10px',
                backdropFilter: 'blur(16px)',
                fontFamily: "'Space Grotesk', sans-serif",
                fontSize: '0.875rem',
                boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
              },
              success: {
                iconTheme: { primary: '#FFFFFF', secondary: '#000000' },
              },
              error: {
                iconTheme: { primary: '#ff4757', secondary: '#000' },
              },
            }}
          />
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
          <Footer />
          {user && <CameraWidget />}
        </div>
      </BrowserRouter>
    </WebSocketProvider>
  );
}

export default App;
