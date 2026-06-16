import React, { useEffect, useState } from 'react';
import { createTicket, getMyTickets } from '../services/api';

const CATEGORIES = [
  { value: 'general', label: 'Général' },
  { value: 'billing', label: 'Abonnement / Offre' },
  { value: 'bug', label: 'Bug / Problème' },
  { value: 'feature', label: 'Suggestion' },
];

const STATUS_LABEL = {
  open: { text: 'Ouvert', color: '#fbbf24' },
  in_progress: { text: 'En cours', color: '#38bdf8' },
  closed: { text: 'Résolu', color: '#34d399' },
};

export default function Support() {
  const [tickets, setTickets] = useState([]);
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [category, setCategory] = useState('general');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [sending, setSending] = useState(false);

  const load = () => {
    getMyTickets()
      .then((res) => setTickets(res.data || []))
      .catch(() => {});
  };

  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError(''); setSuccess('');
    if (subject.trim().length < 3 || message.trim().length < 5) {
      setError('Sujet (≥3 car.) et message (≥5 car.) requis.');
      return;
    }
    setSending(true);
    try {
      await createTicket({ subject, message, category });
      setSuccess('Ticket envoyé à l\'administrateur.');
      setSubject(''); setMessage(''); setCategory('general');
      load();
    } catch (err) {
      setError(err.response?.data?.detail || 'Envoi impossible.');
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{ maxWidth: 760, margin: '0 auto' }}>
      <h1 style={{ marginBottom: 4 }}>Support</h1>
      <p style={{ color: '#71717a', fontSize: '0.85rem', marginBottom: 20 }}>
        Une question, un bug, une demande de changement d'offre ? Envoyez un ticket à l'équipe.
      </p>

      <form onSubmit={submit} className="card" style={{ marginBottom: 28 }}>
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <input
              type="text" placeholder="Sujet" value={subject}
              onChange={(e) => setSubject(e.target.value)}
              style={{ flex: 2, minWidth: 200 }}
            />
            <select value={category} onChange={(e) => setCategory(e.target.value)} style={{ flex: 1, minWidth: 140 }}>
              {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
          </div>
          <textarea
            placeholder="Décrivez votre demande..." value={message}
            onChange={(e) => setMessage(e.target.value)} rows={5}
            style={{ resize: 'vertical' }}
          />
          {error && <span style={{ color: '#f87171', fontSize: '0.82rem' }}>{error}</span>}
          {success && <span style={{ color: '#34d399', fontSize: '0.82rem' }}>{success}</span>}
          <button type="submit" className="btn-primary" disabled={sending} style={{ justifySelf: 'start' }}>
            {sending ? 'Envoi...' : 'Envoyer le ticket'}
          </button>
        </div>
      </form>

      <h3 style={{ marginBottom: 12 }}>Mes tickets</h3>
      {tickets.length === 0 ? (
        <p style={{ color: '#71717a', fontSize: '0.85rem' }}>Aucun ticket pour le moment.</p>
      ) : (
        <div style={{ display: 'grid', gap: 10 }}>
          {tickets.map((t) => {
            const st = STATUS_LABEL[t.status] || STATUS_LABEL.open;
            return (
              <div key={t.id} className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <strong>{t.subject}</strong>
                  <span style={{ color: st.color, fontSize: '0.75rem', border: `1px solid ${st.color}55`, padding: '2px 8px', borderRadius: 10 }}>
                    {st.text}
                  </span>
                </div>
                <p style={{ color: '#a1a1aa', fontSize: '0.84rem', marginTop: 6 }}>{t.message}</p>
                {t.admin_response && (
                  <div style={{ marginTop: 10, padding: 10, background: 'rgba(82,113,255,0.08)', borderRadius: 8, borderLeft: '3px solid #5271ff' }}>
                    <span style={{ fontSize: '0.72rem', color: '#5271ff', textTransform: 'uppercase' }}>Réponse de l'équipe</span>
                    <p style={{ fontSize: '0.84rem', marginTop: 4 }}>{t.admin_response}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
