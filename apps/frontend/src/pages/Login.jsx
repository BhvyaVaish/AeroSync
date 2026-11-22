import { useState } from 'react';
import { toast } from 'react-hot-toast';
import { GlassCard } from '../components/GlassCard';
import { Button } from '../components/Button';
import { LogIn } from 'lucide-react';
import { api } from '../services/api';
import './Login.css';

export const Login = () => {
  const [isRegistering, setIsRegistering] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      if (isRegistering) {
        await api.auth.register(email, password, displayName || email.split('@')[0]);
        toast.success('Registration successful!');
      } else {
        await api.auth.login(email, password);
        toast.success('Welcome back!');
      }
      window.location.href = '/';
    } catch (err) {
      toast.error(err.message || 'Authentication failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-container">
      <GlassCard className="login-card">
        <div className="login-header">
          <div className="login-pill-badge">
            <span className="pill-dot" />
            <span>AEROSYNC AUTHENTICATION</span>
          </div>
          <h2>{isRegistering ? 'Create Account' : 'Welcome to AeroSync'}</h2>
          <p>Stealth Workspace Telemetry & Synchronization</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label>Email Address</label>
            <input
              type="email"
              placeholder="operator@aerosync.io"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          {isRegistering && (
            <div className="form-group">
              <label>Display Name</label>
              <input
                type="text"
                placeholder="Jane Doe"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>
          )}
          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              placeholder="••••••••"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <Button
            variant="primary"
            size="lg"
            className="full-width mt-4"
            type="submit"
            icon={<LogIn size={18} />}
            disabled={isLoading}
          >
            {isLoading ? 'Processing…' : (isRegistering ? 'Sign Up' : 'Sign In')}
          </Button>
        </form>

        <div className="login-footer">
          <p>
            {isRegistering ? 'Already have an account?' : "Don't have an account?"}
            <button
              className="text-btn"
              type="button"
              onClick={() => setIsRegistering(!isRegistering)}
            >
              {isRegistering ? 'Sign In' : 'Sign Up'}
            </button>
          </p>
        </div>
      </GlassCard>
    </div>
  );
};
