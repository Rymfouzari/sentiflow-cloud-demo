import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend, LabelList,
} from 'recharts';
import { getAnalyticsDashboard } from '../services/api';
import { Lock, TrendingUp, TrendingDown, Info } from 'lucide-react';
import './Dashboard.css';

const PIE_COLORS = ['#5271ff', '#34d399', '#f87171', '#fbbf24', '#38bdf8', '#fb923c', '#a78bfa'];
const CLUSTER_COLORS = ['#5271ff', '#34d399', '#fbbf24', '#fb923c', '#a78bfa'];

function corrColor(v) {
  if (v >= 0) return `rgba(82, 113, 255, ${0.12 + Math.min(1, v) * 0.72})`;
  return `rgba(248, 113, 113, ${0.12 + Math.min(1, -v) * 0.72})`;
}
function simLabel(v) {
  if (v >= 0.8) return 'Très similaire';
  if (v >= 0.5) return 'Similaire';
  if (v >= 0.1) return 'Peu similaire';
  if (v > -0.1) return 'Différent';
  return 'Opposé';
}

function KpiCard({ label, value, sub, trend }) {
  return (
    <div className="metric-card">
      <span className="metric-value">{value}</span>
      <span className="metric-label">{label}</span>
      {sub && <span style={{ fontSize: '0.72rem', color: '#71717a', marginTop: 2 }}>{sub}</span>}
      {trend !== null && trend !== undefined && (
        <span style={{ fontSize: '0.72rem', marginTop: 2, color: trend >= 0 ? '#34d399' : '#f87171', display: 'flex', alignItems: 'center', gap: 3 }}>
          {trend >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
          {trend >= 0 ? '+' : ''}{trend}% vs période préc.
        </span>
      )}
    </div>
  );
}

function Section({ title, hint, children }) {
  return (
    <div className="chart-card" style={{ marginBottom: 18 }}>
      <h3>{title}</h3>
      {hint && (
        <p style={{ color: '#71717a', fontSize: '0.78rem', marginTop: -4, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 5 }}>
          <Info size={13} /> {hint}
        </p>
      )}
      {children}
    </div>
  );
}

function Upgrade({ message }) {
  return (
    <div className="card" style={{ textAlign: 'center', padding: 40 }}>
      <Lock size={32} color="#5271ff" style={{ marginBottom: 12 }} />
      <h2 style={{ marginBottom: 8 }}>Fonctionnalité réservée</h2>
      <p style={{ color: '#a1a1aa', marginBottom: 20 }}>{message}</p>
      <Link to="/pricing" className="btn-primary">Voir les offres</Link>
    </div>
  );
}

const TONE_STYLE = {
  positive: { bg: 'rgba(52,211,153,0.08)', border: '#34d39955', color: '#34d399' },
  negative: { bg: 'rgba(248,113,113,0.08)', border: '#f8717155', color: '#f87171' },
  neutral: { bg: 'rgba(82,113,255,0.08)', border: '#5271ff55', color: '#93c5fd' },
};

function InsightsPanel({ insights }) {
  if (!insights || !insights.length) return null;
  return (
    <div className="chart-card" style={{ marginBottom: 18, background: 'linear-gradient(135deg, #111118, #0f0f14)' }}>
      <h3 style={{ marginBottom: 4 }}>Ce qu'il faut retenir</h3>
      <p style={{ color: '#71717a', fontSize: '0.78rem', marginBottom: 14 }}>
        Synthèse automatique en langage clair, générée à partir des analyses ci-dessous.
      </p>
      <div style={{ display: 'grid', gap: 8 }}>
        {insights.map((ins, i) => {
          const st = TONE_STYLE[ins.tone] || TONE_STYLE.neutral;
          return (
            <div key={i} style={{
              display: 'flex', alignItems: 'flex-start', gap: 10,
              padding: '10px 12px', borderRadius: 8,
              background: st.bg, border: `1px solid ${st.border}`,
            }}>
              <span style={{ fontSize: '1.1rem', lineHeight: 1.2 }}>{ins.icon}</span>
              <span style={{ fontSize: '0.86rem', color: '#e4e4e7', lineHeight: 1.45 }}>{ins.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [locked, setLocked] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true); setError(''); setLocked(null);
    getAnalyticsDashboard(days)
      .then((res) => setData(res.data))
      .catch((e) => {
        if (e.response?.status === 403) setLocked(e.response.data?.detail || 'Offre insuffisante.');
        else setError(e.response?.data?.detail || 'Erreur de chargement.');
      })
      .finally(() => setLoading(false));
  }, [days]);

  if (loading) return <p style={{ color: '#52525b' }}>Chargement des analyses...</p>;
  if (locked) return <Upgrade message={locked} />;
  if (error) return <div className="card" style={{ color: '#f87171' }}>{error}</div>;
  if (!data) return null;

  if (!data.has_data) {
    return (
      <div>
        <h1>Dashboard</h1>
        <p className="info-msg">{data.message}</p>
      </div>
    );
  }

  const k = data.kpis;
  const advanced = data.plan_advanced;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <h1 style={{ marginBottom: 4 }}>Dashboard analytique</h1>
          <p style={{ color: '#52525b', fontSize: '0.85rem' }}>Veille de réputation & d'opinion — {data.targets_breakdown.length} sujet(s) suivi(s)</p>
        </div>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>7 jours</option>
          <option value={14}>14 jours</option>
          <option value={30}>30 jours</option>
          <option value={90}>90 jours</option>
        </select>
      </div>

      {/* Insights en clair — en tête */}
      <div style={{ marginTop: 16 }}>
        <InsightsPanel insights={data.insights} />
      </div>

      {/* KPIs */}
      <div className="metrics">
        <KpiCard label="Tweets analysés" value={k.total_tweets} trend={k.volume_trend_pct} />
        <KpiCard label="Score de sentiment net" value={`${k.net_score >= 0 ? '+' : ''}${(k.net_score * 100).toFixed(0)}`} sub="0 = neutre, +100 = très positif" />
        <KpiCard label="Positif" value={`${k.positive_pct}%`} />
        <KpiCard label="Négatif" value={`${k.negative_pct}%`} />
        <KpiCard label="Fiabilité analyse" value={`${(k.avg_confidence * 100).toFixed(0)}%`} sub="confiance du modèle" />
      </div>

      {/* Timeline */}
      <Section title="Évolution dans le temps" hint="Comment le volume de tweets positifs / négatifs évolue jour après jour. Un pic de rouge = alerte.">
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={data.timeline}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
            <XAxis dataKey="date" tick={{ fill: '#71717a', fontSize: 10 }} />
            <YAxis tick={{ fill: '#71717a', fontSize: 11 }} />
            <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 8 }} />
            <Legend />
            <Area type="monotone" dataKey="positive" name="Positif" stackId="1" stroke="#34d399" fill="#34d39966" />
            <Area type="monotone" dataKey="neutral" name="Neutre" stackId="1" stroke="#71717a" fill="#71717a55" />
            <Area type="monotone" dataKey="negative" name="Négatif" stackId="1" stroke="#f87171" fill="#f8717166" />
          </AreaChart>
        </ResponsiveContainer>
      </Section>

      <div className="charts">
        <Section title="Quel sujet est le mieux perçu ?" hint="Volume de tweets positifs (vert) vs négatifs (rouge) pour chaque sujet.">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={data.targets_breakdown} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis type="number" tick={{ fill: '#71717a', fontSize: 11 }} />
              <YAxis type="category" dataKey="name" width={80} tick={{ fill: '#a1a1aa', fontSize: 11 }} />
              <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 8 }} />
              <Legend />
              <Bar dataKey="positive" name="Positif" fill="#34d399" stackId="a" />
              <Bar dataKey="negative" name="Négatif" fill="#f87171" stackId="a" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Section>

        <Section title="Qui fait le plus parler ?" hint="Part de chaque sujet dans le volume total de conversation.">
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie data={data.share_of_voice} dataKey="volume" nameKey="name" cx="50%" cy="50%" outerRadius={95} label>
                {data.share_of_voice.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 8 }} />
            </PieChart>
          </ResponsiveContainer>
        </Section>
      </div>

      {/* Drivers / mots-clés */}
      <Section title="Pourquoi ces réactions ? (mots-clés)" hint="Les mots les plus caractéristiques des tweets positifs et négatifs. Ce sont les vrais déclencheurs d'opinion.">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div>
            <h4 style={{ color: '#34d399', fontSize: '0.85rem', marginBottom: 8 }}>Ce qui plaît</h4>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {data.keywords.positive.length === 0 && <span style={{ color: '#71717a', fontSize: '0.8rem' }}>—</span>}
              {data.keywords.positive.map((w) => (
                <span key={w.word} style={{ background: '#34d39922', color: '#34d399', padding: '3px 8px', borderRadius: 8, fontSize: `${Math.min(1.1, 0.72 + w.count / 30)}rem` }}>
                  {w.word}
                </span>
              ))}
            </div>
          </div>
          <div>
            <h4 style={{ color: '#f87171', fontSize: '0.85rem', marginBottom: 8 }}>Ce qui fâche</h4>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {data.keywords.negative.length === 0 && <span style={{ color: '#71717a', fontSize: '0.8rem' }}>—</span>}
              {data.keywords.negative.map((w) => (
                <span key={w.word} style={{ background: '#f8717122', color: '#f87171', padding: '3px 8px', borderRadius: 8, fontSize: `${Math.min(1.1, 0.72 + w.count / 30)}rem` }}>
                  {w.word}
                </span>
              ))}
            </div>
          </div>
        </div>
      </Section>

      {/* Carte des sujets (PCA + clusters) */}
      <Section title="Carte des sujets" hint="Deux sujets proches sur la carte = les gens en parlent avec le même état d'esprit. Les couleurs regroupent les sujets qui se ressemblent.">
        {!advanced ? (
          <Upgrade message="La carte des sujets et l'analyse de similarité sont réservées à l'offre Premium." />
        ) : !data.pca.available ? (
          <p style={{ color: '#71717a', fontSize: '0.85rem' }}>{data.pca.message}</p>
        ) : (
          <TopicMap pca={data.pca} />
        )}
      </Section>

      {/* Similarité (corrélation reformulée) */}
      <Section title="Quels sujets se ressemblent ?" hint="Plus la case est bleue, plus les deux sujets suscitent le même type de réactions. Rouge = réactions opposées.">
        {!advanced ? (
          <Upgrade message="L'analyse de similarité est réservée à l'offre Premium." />
        ) : !data.correlation.available ? (
          <p style={{ color: '#71717a', fontSize: '0.85rem' }}>{data.correlation.message}</p>
        ) : (
          <SimilarityHeatmap corr={data.correlation} />
        )}
      </Section>
    </div>
  );
}

function TopicMap({ pca }) {
  const groups = (pca.clusters || []).filter((c) => c.members.length);
  return (
    <div>
      <ResponsiveContainer width="100%" height={360}>
        <ScatterChart margin={{ top: 20, right: 30, bottom: 10, left: 10 }}>
          <CartesianGrid stroke="#1c1c22" />
          <XAxis type="number" dataKey="x" hide />
          <YAxis type="number" dataKey="y" hide />
          <ZAxis range={[160, 160]} />
          <Tooltip cursor={{ strokeDasharray: '3 3' }} contentStyle={{ background: '#18181b', border: '1px solid #27272a', borderRadius: 8 }}
            formatter={() => ['', '']} labelFormatter={() => ''} />
          <Scatter data={pca.points}>
            <LabelList dataKey="name" position="top" style={{ fill: '#e4e4e7', fontSize: 11 }} />
            {pca.points.map((p, i) => <Cell key={i} fill={CLUSTER_COLORS[p.cluster % CLUSTER_COLORS.length]} />)}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      {/* Légende des familles */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 8 }}>
        {groups.map((g) => (
          <div key={g.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', color: '#a1a1aa' }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: CLUSTER_COLORS[g.id % CLUSTER_COLORS.length], display: 'inline-block' }} />
            Famille {g.id + 1} : {g.members.join(', ')}
          </div>
        ))}
      </div>
    </div>
  );
}

function SimilarityHeatmap({ corr }) {
  const { labels, matrix } = corr;
  const cell = 46;
  return (
    <div style={{ overflowX: 'auto' }}>
      <div style={{ display: 'inline-block' }}>
        <div style={{ display: 'flex', marginLeft: 90 }}>
          {labels.map((l) => (
            <div key={l} style={{ width: cell, fontSize: '0.7rem', color: '#a1a1aa', textAlign: 'center', transform: 'rotate(-35deg)', transformOrigin: 'center', height: 40 }}>{l}</div>
          ))}
        </div>
        {matrix.map((row, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center' }}>
            <div style={{ width: 90, fontSize: '0.72rem', color: '#a1a1aa', textAlign: 'right', paddingRight: 8 }}>{labels[i]}</div>
            {row.map((v, j) => (
              <div key={j} title={`${labels[i]} ↔ ${labels[j]} : ${simLabel(v)}`}
                style={{
                  width: cell, height: cell, background: corrColor(v),
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '0.68rem', color: '#e4e4e7', border: '1px solid #18181b', cursor: 'default',
                }}>
                {i === j ? '—' : v.toFixed(1)}
              </div>
            ))}
          </div>
        ))}
        <div style={{ display: 'flex', gap: 16, marginTop: 10, fontSize: '0.74rem', color: '#71717a' }}>
          <span><span style={{ display: 'inline-block', width: 10, height: 10, background: corrColor(0.9), marginRight: 5 }} /> Se ressemblent</span>
          <span><span style={{ display: 'inline-block', width: 10, height: 10, background: corrColor(-0.6), marginRight: 5 }} /> Opposés</span>
          <span>Survolez une case pour le détail.</span>
        </div>
      </div>
    </div>
  );
}
