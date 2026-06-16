import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Check, X, Zap } from 'lucide-react';
import { getMyPlan } from '../services/api';

const ORDER = ['free', 'standard', 'premium'];

export default function Pricing() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getMyPlan()
      .then((res) => setData(res.data))
      .catch((e) => setError(e.response?.data?.detail || 'Impossible de charger les offres.'));
  }, []);

  if (error) return <div className="card" style={{ color: '#f87171' }}>{error}</div>;
  if (!data) return <p style={{ color: '#71717a' }}>Chargement...</p>;

  const { current, quota, catalog } = data;
  const currentPlan = current?.plan;

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto' }}>
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <h1 style={{ marginBottom: 8 }}>Offres SentiFlow</h1>
        <p style={{ color: '#71717a' }}>
          Votre offre actuelle : <strong style={{ color: '#5271ff' }}>{catalog[currentPlan]?.label}</strong>
          {quota && !quota.unlimited && (
            <> — {quota.remaining}/{quota.limit} appels IA restants aujourd'hui</>
          )}
          {quota && quota.unlimited && <> — appels IA illimités</>}
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 18 }}>
        {ORDER.map((key) => {
          const plan = catalog[key];
          if (!plan) return null;
          const isCurrent = key === currentPlan;
          const highlight = key === 'premium';
          return (
            <div
              key={key}
              className="card"
              style={{
                border: isCurrent ? '2px solid #5271ff' : highlight ? '1px solid #5271ff55' : '1px solid #27272a',
                position: 'relative',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              {isCurrent && (
                <span style={{
                  position: 'absolute', top: -11, left: '50%', transform: 'translateX(-50%)',
                  background: '#5271ff', color: 'white', fontSize: '0.7rem', padding: '2px 10px', borderRadius: 12,
                }}>Offre actuelle</span>
              )}
              <h3 style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                {highlight && <Zap size={16} color="#fbbf24" />} {plan.label}
              </h3>
              <div style={{ margin: '12px 0' }}>
                <span style={{ fontSize: '1.8rem', fontWeight: 700 }}>{plan.price_eur}€</span>
                <span style={{ color: '#71717a', fontSize: '0.85rem' }}> / mois</span>
              </div>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0, flex: 1 }}>
                {plan.features.map((f, i) => (
                  <li key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 8, fontSize: '0.85rem' }}>
                    <Check size={15} color="#34d399" style={{ flexShrink: 0, marginTop: 2 }} /> {f}
                  </li>
                ))}
                {plan.limitations.map((f, i) => (
                  <li key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 8, fontSize: '0.85rem', color: '#71717a' }}>
                    <X size={15} color="#f87171" style={{ flexShrink: 0, marginTop: 2 }} /> {f}
                  </li>
                ))}
              </ul>
              <div style={{ marginTop: 16 }}>
                {isCurrent ? (
                  <button className="btn-primary" disabled style={{ width: '100%', opacity: 0.6 }}>
                    Offre active
                  </button>
                ) : (
                  <Link to="/support" className="btn-primary" style={{ width: '100%', textAlign: 'center', display: 'block' }}>
                    Demander cette offre
                  </Link>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <p style={{ color: '#71717a', fontSize: '0.8rem', textAlign: 'center', marginTop: 24 }}>
        Le changement d'offre se fait via une demande au support (un administrateur l'active).
      </p>
    </div>
  );
}
