import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { login as apiLogin, register as apiRegister } from '../services/api';

export default function Login() {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { loginUser } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isRegister) {
        const res = await apiRegister(email, username, password);
        loginUser(res.data.access_token, res.data.user);
        navigate('/assistant');
      } else {
        const res = await apiLogin(email, password);
        loginUser(res.data.access_token, res.data.user);
        navigate('/assistant');
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Erreur de connexion');
    } finally {
      setLoading(false);
    }
  };

  const inputStyle = {
    width: '100%',
    padding: '12px 14px',
    background: '#0f0f12',
    border: '1px solid #27272a',
    borderRadius: 8,
    color: '#fafafa',
    fontSize: '0.9rem',
    outline: 'none',
  };

  return (
    <div style={{ maxWidth: 380, margin: '80px auto' }}>
      <h1 style={{ marginBottom: 8 }}>{isRegister ? 'Creer un compte' : 'Connexion'}</h1>
      <p style={{ color: '#52525b', fontSize: '0.85rem', marginBottom: 28 }}>
        {isRegister ? 'Inscris-toi pour utiliser SentiFlow' : 'Connecte-toi a ton compte'}
      </p>

      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: 14 }}>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            style={inputStyle}
          />
        </div>

        {isRegister && (
          <div style={{ marginBottom: 14 }}>
            <input
              type="text"
              placeholder="Nom d'utilisateur"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              style={inputStyle}
            />
          </div>
        )}

        <div style={{ marginBottom: 20 }}>
          <input
            type="password"
            placeholder="Mot de passe"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            style={inputStyle}
          />
        </div>

        {error && (
          <p style={{ color: '#f87171', fontSize: '0.82rem', marginBottom: 14 }}>{error}</p>
        )}

        <button
          type="submit"
          disabled={loading}
          style={{
            width: '100%',
            padding: '12px',
            background: '#5271ff',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            fontWeight: 600,
            fontSize: '0.9rem',
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading ? 'Chargement...' : (isRegister ? "S'inscrire" : 'Se connecter')}
        </button>
      </form>

      <p style={{ marginTop: 20, color: '#71717a', fontSize: '0.82rem', textAlign: 'center' }}>
        {isRegister ? 'Deja un compte ? ' : 'Pas de compte ? '}
        <button
          onClick={() => { setIsRegister(!isRegister); setError(''); }}
          style={{ background: 'none', border: 'none', color: '#5271ff', fontSize: '0.82rem', textDecoration: 'underline' }}
        >
          {isRegister ? 'Se connecter' : "S'inscrire"}
        </button>
      </p>
    </div>
  );
}
