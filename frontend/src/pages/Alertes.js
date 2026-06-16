import React, { useEffect, useState } from 'react';
import { getAlerts, createAlert, getTargets } from '../services/api';
import { Plus } from 'lucide-react';

export default function Alertes() {
  const [alerts, setAlerts] = useState([]);
  const [targets, setTargets] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ target_id: '', sentiment: 'colere', threshold: 30 });
  const [message, setMessage] = useState('');

  useEffect(() => {
    getAlerts().then((res) => setAlerts(res.data)).catch(() => {});
    getTargets().then((res) => setTargets(res.data)).catch(() => {});
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.target_id) return;
    try {
      await createAlert({
        target_id: Number(form.target_id),
        sentiment: form.sentiment,
        threshold: Number(form.threshold) / 100,
      });
      setMessage('Alerte creee');
      setShowForm(false);
      getAlerts().then((res) => setAlerts(res.data));
    } catch (err) {
      setMessage(err?.response?.data?.detail || 'Erreur');
    }
    setTimeout(() => setMessage(''), 3000);
  };

  return (
    <div style={{ maxWidth: 600 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ marginBottom: 4 }}>Alertes</h1>
          <p style={{ color: '#52525b', fontSize: '0.85rem' }}>
            Notification quand un sentiment depasse un seuil
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          style={{
            padding: '8px 14px',
            background: '#5271ff',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            fontWeight: 600,
            fontSize: '0.82rem',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <Plus size={14} /> Nouvelle
        </button>
      </div>

      {message && (
        <div style={{ padding: '10px 14px', background: '#0f0f12', border: '1px solid #27272a', borderRadius: 8, marginBottom: 16, fontSize: '0.82rem', color: '#a1a1aa' }}>
          {message}
        </div>
      )}

      {showForm && (
        <form onSubmit={handleCreate} style={{
          padding: 20,
          background: '#0f0f12',
          border: '1px solid #1c1c22',
          borderRadius: 10,
          marginBottom: 20,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}>
          <select
            value={form.target_id}
            onChange={(e) => setForm({ ...form, target_id: e.target.value })}
            style={{ padding: '10px 14px', background: '#09090b', border: '1px solid #27272a', borderRadius: 8, color: '#e4e4e7' }}
          >
            <option value="">Choisir une cible</option>
            {targets.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <div style={{ display: 'flex', gap: 10 }}>
            <select
              value={form.sentiment}
              onChange={(e) => setForm({ ...form, sentiment: e.target.value })}
              style={{ flex: 1, padding: '10px 14px', background: '#09090b', border: '1px solid #27272a', borderRadius: 8, color: '#e4e4e7' }}
            >
              <option value="colere">Colere</option>
              <option value="tristesse">Tristesse</option>
              <option value="peur">Peur</option>
              <option value="joie">Joie</option>
            </select>
            <input
              type="number"
              value={form.threshold}
              onChange={(e) => setForm({ ...form, threshold: e.target.value })}
              min={5}
              max={100}
              placeholder="Seuil %"
              style={{ width: 100, padding: '10px 14px', background: '#09090b', border: '1px solid #27272a', borderRadius: 8, color: '#e4e4e7' }}
            />
          </div>
          <button type="submit" style={{ padding: '10px', background: '#5271ff', color: 'white', border: 'none', borderRadius: 8, fontWeight: 600 }}>
            Creer l'alerte
          </button>
        </form>
      )}

      <div>
        {alerts.map((alert, i) => (
          <div key={i} style={{
            padding: '14px 16px',
            background: '#0f0f12',
            border: '1px solid #1c1c22',
            borderRadius: 10,
            marginBottom: 8,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}>
            <div>
              <span style={{ color: '#fafafa', fontSize: '0.9rem' }}>
                {alert.target_name || `Cible #${alert.target_id}`}
              </span>
              <span style={{ marginLeft: 12, color: '#71717a', fontSize: '0.8rem' }}>
                {alert.sentiment} &gt; {((alert.threshold || 0) * 100).toFixed(0)}%
              </span>
            </div>
            <span style={{ color: alert.triggered ? '#f87171' : '#52525b', fontSize: '0.75rem' }}>
              {alert.triggered ? 'Declenchee' : 'Active'}
            </span>
          </div>
        ))}
        {alerts.length === 0 && (
          <p style={{ color: '#52525b', textAlign: 'center', padding: 30, fontSize: '0.88rem' }}>
            Aucune alerte configuree.
          </p>
        )}
      </div>
    </div>
  );
}
