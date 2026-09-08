import React, { useState } from 'react';

interface LoginModalProps {
  onLogin: (email: string, pass: string) => Promise<void>;
}

export const LoginModal: React.FC<LoginModalProps> = ({ onLogin }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await onLogin(email, password);
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          <span className="mercury-glyph">☿</span>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 800, marginTop: '0.5rem', color: '#fff' }}>
            Mercury Hive
          </h2>
          <p style={{ fontSize: '0.8rem', color: 'var(--accent-cyan)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Sovereign Owner Authentication
          </p>
        </div>

        {error && (
          <div
            style={{
              padding: '0.75rem',
              background: 'rgba(239, 68, 68, 0.15)',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              borderRadius: '8px',
              color: '#ef4444',
              fontSize: '0.85rem',
              marginBottom: '1rem',
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Owner Email Address
            </label>
            <input
              type="email"
              className="input-field"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="owner@mercuryhive.internal"
            />
          </div>

          <div>
            <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Master Security Passphrase
            </label>
            <input
              type="password"
              className="input-field"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder="••••••••••••••••"
            />
          </div>

          <button
            type="submit"
            className="btn-killswitch"
            style={{
              width: '100%',
              justifyContent: 'center',
              background: 'linear-gradient(135deg, #0284c7, #0369a1)',
              boxShadow: '0 0 15px rgba(2, 132, 199, 0.4)',
            }}
            disabled={loading}
          >
            {loading ? 'Authenticating...' : 'Access Sovereign Console'}
          </button>
        </form>
      </div>
    </div>
  );
};
