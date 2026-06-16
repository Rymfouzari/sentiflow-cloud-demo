import React, { useEffect, useState } from 'react';
import api from '../services/api';
import { RefreshCw, Play, Square, Database, Cpu, Users, BarChart3, Loader2, LifeBuoy, MessageSquare } from 'lucide-react';

export default function Admin() {
  const [stats, setStats] = useState(null);
  const [dbOverview, setDbOverview] = useState(null);
  const [schedule, setSchedule] = useState(null);
  const [pipelineStatus, setPipelineStatus] = useState(null);
  const [trainingStats, setTrainingStats] = useState(null);
  const [loading, setLoading] = useState({});
  const [message, setMessage] = useState('');

  const loadAll = async () => {
    try {
      const [statsRes, dbRes, schedRes, pipeRes, trainRes] = await Promise.allSettled([
        api.get('/admin/stats'),
        api.get('/admin/db/overview'),
        api.get('/admin/celery/schedule'),
        api.get('/admin/pipeline/status'),
        api.get('/admin/training-data/stats'),
      ]);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
      if (dbRes.status === 'fulfilled') setDbOverview(dbRes.value.data);
      if (schedRes.status === 'fulfilled') setSchedule(schedRes.value.data);
      if (pipeRes.status === 'fulfilled') setPipelineStatus(pipeRes.value.data);
      if (trainRes.status === 'fulfilled') setTrainingStats(trainRes.value.data);
    } catch (err) {
      setMessage('Erreur chargement admin');
    }
  };

  useEffect(() => { loadAll(); }, []);

  const doAction = async (key, fn) => {
    setLoading((prev) => ({ ...prev, [key]: true }));
    setMessage('');
    try {
      const res = await fn();
      setMessage(res.data?.message || 'OK');
      loadAll();
      // Notifier le timer de la sidebar pour refresh instantané
      window.dispatchEvent(new Event('sentiflow:refresh-timer'));
    } catch (err) {
      setMessage(err?.response?.data?.detail || 'Erreur');
    } finally {
      setLoading((prev) => ({ ...prev, [key]: false }));
    }
  };

  const cardStyle = { background: '#0f0f12', border: '1px solid #1c1c22', borderRadius: 12, padding: 20 };
  const labelStyle = { color: '#52525b', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.05em' };
  const valueStyle = { color: '#fafafa', fontSize: '1.5rem', fontWeight: 700 };
  const btnStyle = (color = '#5271ff') => ({
    padding: '8px 14px', background: 'transparent', border: `1px solid ${color}33`,
    borderRadius: 6, color, fontSize: '0.78rem', fontWeight: 500,
    display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer',
  });

  return (
    <div className="animate-in" style={{ maxWidth: 900 }}>
      <h1 style={{ marginBottom: 4 }}>Administration</h1>
      <p style={{ color: '#52525b', fontSize: '0.85rem', marginBottom: 28 }}>
        Controle complet : pipeline, collecte, analyse, BDD
      </p>

      {message && (
        <div style={{ padding: '10px 14px', background: '#0f0f12', border: '1px solid #27272a', borderRadius: 8, marginBottom: 16, fontSize: '0.82rem', color: '#a1a1aa' }}>
          {message}
        </div>
      )}

      {/* Vue d'ensemble BDD */}
      {dbOverview && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 28 }}>
          <div style={cardStyle}>
            <p style={labelStyle}>Tweets total</p>
            <p style={valueStyle}>{dbOverview.tweets?.total || 0}</p>
            <p style={{ color: '#71717a', fontSize: '0.72rem' }}>{dbOverview.tweets?.pending || 0} en attente</p>
          </div>
          <div style={cardStyle}>
            <p style={labelStyle}>Analyses</p>
            <p style={valueStyle}>{dbOverview.tweets?.analyzed || 0}</p>
          </div>
          <div style={cardStyle}>
            <p style={labelStyle}>Cibles</p>
            <p style={valueStyle}>{dbOverview.targets || 0}</p>
          </div>
          <div style={cardStyle}>
            <p style={labelStyle}>Utilisateurs</p>
            <p style={valueStyle}>{dbOverview.users || 0}</p>
          </div>
        </div>
      )}

      {/* Usage API */}
      {dbOverview?.api_usage && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12, marginBottom: 28 }}>
          <div style={cardStyle}>
            <p style={labelStyle}>Appels Groq (LLM)</p>
            <p style={valueStyle}>{dbOverview.api_usage.groq_calls}</p>
            <p style={{ color: '#71717a', fontSize: '0.72rem' }}>Depuis le dernier reset</p>
          </div>
          <div style={cardStyle}>
            <p style={labelStyle}>Appels Twitter API</p>
            <p style={valueStyle}>{dbOverview.api_usage.twitter_calls}</p>
            <p style={{ color: '#71717a', fontSize: '0.72rem' }}>
              <button onClick={() => doAction('resetUsage', () => api.post('/admin/usage/reset'))} style={{ background: 'none', border: 'none', color: '#5271ff', fontSize: '0.72rem', cursor: 'pointer', textDecoration: 'underline' }}>
                Remettre a zero
              </button>
            </p>
          </div>
        </div>
      )}

      {/* Celery / Collecte */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <RefreshCw size={18} color="#5271ff" /> Collecte et Analyse (Celery)
        </h2>
        <div style={cardStyle}>
          {schedule && (
            <div style={{ marginBottom: 16 }}>
              <p style={{ color: '#a1a1aa', fontSize: '0.82rem', marginBottom: 8 }}>Schedule actuel :</p>
              {Object.entries(schedule).map(([name, config]) => (
                <div key={name} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #1c1c22' }}>
                  <span style={{ color: '#e4e4e7', fontSize: '0.82rem' }}>{name}</span>
                  <span style={{ color: '#71717a', fontSize: '0.78rem' }}>
                    {typeof config.interval_minutes === 'number' ? `${config.interval_minutes} min` : config.interval_minutes}
                  </span>
                </div>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button style={btnStyle('#5271ff')} onClick={() => doAction('collect', () => api.post('/admin/celery/collect-now'))} disabled={loading.collect}>
              {loading.collect ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Play size={14} />} Collecter maintenant
            </button>
            <button style={btnStyle('#5271ff')} onClick={() => doAction('analyze', () => api.post('/admin/celery/analyze-now'))} disabled={loading.analyze}>
              {loading.analyze ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Cpu size={14} />} Analyser maintenant
            </button>
            <button style={btnStyle('#f87171')} onClick={() => doAction('stop', () => api.post('/admin/celery/stop-collect'))}>
              <Square size={14} /> Stopper collecte auto
            </button>
            <select
              id="interval-select"
              defaultValue="15"
              style={{ padding: '6px 10px', background: '#09090b', border: '1px solid #27272a', borderRadius: 6, color: '#e4e4e7', fontSize: '0.78rem' }}
            >
              <option value="5">5 min</option>
              <option value="10">10 min</option>
              <option value="15">15 min</option>
              <option value="30">30 min</option>
              <option value="60">1h</option>
              <option value="120">2h</option>
            </select>
            <button style={btnStyle('#34d399')} onClick={() => {
              const val = document.getElementById('interval-select').value;
              doAction('start', () => api.post(`/admin/celery/start-collect?interval_minutes=${val}`));
            }}>
              <Play size={14} /> Reactiver
            </button>
          </div>
        </div>
      </section>

      {/* Pipeline TinyGPT */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Cpu size={18} color="#5271ff" /> Pipeline TinyGPT (Entrainement)
        </h2>
        <div style={cardStyle}>
          {pipelineStatus?.last_eval && (
            <div style={{ marginBottom: 16 }}>
              <p style={{ color: '#a1a1aa', fontSize: '0.82rem', marginBottom: 8 }}>Dernier entrainement :</p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                <div>
                  <p style={labelStyle}>Score ancien</p>
                  <p style={{ color: '#e4e4e7', fontSize: '1rem', fontWeight: 600 }}>{(pipelineStatus.last_eval.old_score * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p style={labelStyle}>Score nouveau</p>
                  <p style={{ color: '#e4e4e7', fontSize: '1rem', fontWeight: 600 }}>{(pipelineStatus.last_eval.new_score * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p style={labelStyle}>Remplace</p>
                  <p style={{ color: pipelineStatus.last_eval.replaced ? '#34d399' : '#f87171', fontSize: '1rem', fontWeight: 600 }}>
                    {pipelineStatus.last_eval.replaced ? 'Oui' : 'Non'}
                  </p>
                </div>
              </div>
            </div>
          )}
          {trainingStats && (
            <div style={{ marginBottom: 16 }}>
              <p style={{ color: '#a1a1aa', fontSize: '0.82rem', marginBottom: 8 }}>Données qui alimenteront le ré-entraînement :</p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 10 }}>
                <div style={{ background: '#09090b', border: '1px solid #1c1c22', borderRadius: 8, padding: 10 }}>
                  <p style={labelStyle}>Questions loggées</p>
                  <p style={{ color: '#fafafa', fontSize: '1.2rem', fontWeight: 700 }}>{trainingStats.question_logs}</p>
                </div>
                <div style={{ background: '#09090b', border: '1px solid #1c1c22', borderRadius: 8, padding: 10 }}>
                  <p style={labelStyle}>Nouveaux tweets (depuis dernier train)</p>
                  <p style={{ color: '#34d399', fontSize: '1.2rem', fontWeight: 700 }}>{trainingStats.new_tweets_for_training ?? '-'}</p>
                </div>
                <div style={{ background: '#09090b', border: '1px solid #1c1c22', borderRadius: 8, padding: 10 }}>
                  <p style={labelStyle}>Corrections + feedbacks</p>
                  <p style={{ color: '#fafafa', fontSize: '1.2rem', fontWeight: 700 }}>{(trainingStats.user_corrections || 0) + (trainingStats.llm_feedbacks || 0)}</p>
                </div>
              </div>
              <p style={{ color: '#71717a', fontSize: '0.74rem' }}>
                Dernier entraînement : <strong style={{ color: '#a1a1aa' }}>{trainingStats.last_training_at ? trainingStats.last_training_at.slice(0, 16) : 'jamais'}</strong>
                {' · '}Fichier source exécuté : <code style={{ color: '#5271ff' }}>{trainingStats.training_source_file || 'scripts/auto_retrain_pipeline.py'}</code>
              </p>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button style={btnStyle('#5271ff')} onClick={() => doAction('retrain', () => api.post('/admin/pipeline/retrain', { epochs: 4, synthetic_examples: 6000 }))} disabled={loading.retrain}>
              {loading.retrain ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Cpu size={14} />} Lancer entrainement
            </button>
            <button style={btnStyle('#5271ff')} onClick={() => doAction('export', () => api.post('/admin/training-data/export'))} disabled={loading.export}>
              <Database size={14} /> Exporter donnees BDD
            </button>
          </div>
        </div>
      </section>

      {/* Utilisateurs */}
      <section>
        <h2 style={{ fontSize: '1.1rem', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Users size={18} color="#5271ff" /> Utilisateurs
        </h2>
        <div style={cardStyle}>
          <UsersTable />
        </div>
      </section>

      {/* Tickets de support */}
      <section style={{ marginTop: 32 }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <LifeBuoy size={18} color="#5271ff" /> Tickets de support
        </h2>
        <div style={cardStyle}>
          <TicketsAdmin />
        </div>
      </section>

      {/* Logs de questions */}
      <section style={{ marginTop: 32 }}>
        <h2 style={{ fontSize: '1.1rem', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
          <MessageSquare size={18} color="#5271ff" /> Questions des utilisateurs (logs)
        </h2>
        <div style={cardStyle}>
          <QuestionLogs />
        </div>
      </section>
    </div>
  );
}

function AllDashboards() {
  const [dashboards, setDashboards] = useState([]);

  useEffect(() => {
    api.get('/admin/dashboards').then((r) => setDashboards(r.data || [])).catch(() => {});
  }, []);

  if (!dashboards.length) return <p style={{ color: '#52525b', fontSize: '0.82rem' }}>Aucun dashboard genere.</p>;

  return (
    <div style={{ maxHeight: 300, overflowY: 'auto' }}>
      {dashboards.map((d) => (
        <div key={d.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid #1c1c22' }}>
          <div>
            <span style={{ color: '#e4e4e7', fontSize: '0.82rem' }}>{d.title}</span>
            <span style={{ color: '#3f3f46', fontSize: '0.7rem', marginLeft: 8 }}>par {d.user}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: '#52525b', fontSize: '0.7rem' }}>{d.created_at?.slice(0, 16)}</span>
            <a href={`/dashboards/generated/${d.id}`} style={{ fontSize: '0.7rem', color: '#5271ff' }}>Voir</a>
          </div>
        </div>
      ))}
    </div>
  );
}

function UsersTable() {
  const [users, setUsers] = useState([]);
  const [selectedTarget, setSelectedTarget] = useState(null);
  const [tweets, setTweets] = useState([]);
  const [loadingTweets, setLoadingTweets] = useState(false);

  useEffect(() => {
    api.get('/admin/users').then((r) => setUsers(r.data)).catch(() => {});
  }, []);

  const toggleAdmin = async (userId) => {
    try {
      await api.patch(`/admin/users/${userId}/toggle-admin`);
      const res = await api.get('/admin/users');
      setUsers(res.data);
    } catch (err) { /* ignore */ }
  };

  const changePlan = async (userId, plan) => {
    try {
      await api.patch(`/admin/users/${userId}/plan`, { plan });
      const res = await api.get('/admin/users');
      setUsers(res.data);
    } catch (err) { /* ignore */ }
  };

  const viewTweets = async (targetId, targetName) => {
    if (selectedTarget === targetId) {
      setSelectedTarget(null);
      setTweets([]);
      return;
    }
    setSelectedTarget(targetId);
    setLoadingTweets(true);
    try {
      const res = await api.get(`/admin/tweets/${targetId}`);
      setTweets(res.data || []);
    } catch (err) {
      setTweets([]);
    } finally {
      setLoadingTweets(false);
    }
  };

  return (
    <div>
      {users.map((u) => (
        <div key={u.id} style={{ marginBottom: 16, paddingBottom: 16, borderBottom: '1px solid #1c1c22' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <div>
              <span style={{ color: '#e4e4e7', fontSize: '0.9rem', fontWeight: 500 }}>{u.username}</span>
              <span style={{ color: '#52525b', fontSize: '0.75rem', marginLeft: 10 }}>{u.email}</span>
              <span style={{ color: '#3f3f46', fontSize: '0.7rem', marginLeft: 10 }}>
                {u.total_targets} cibles · {u.total_tweets} tweets
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <select
                value={u.plan || 'free'}
                onChange={(e) => changePlan(u.id, e.target.value)}
                style={{ padding: '4px 8px', borderRadius: 4, fontSize: '0.7rem', background: '#09090b', border: '1px solid #27272a', color: '#e4e4e7' }}
              >
                <option value="free">Free</option>
                <option value="standard">Standard</option>
                <option value="premium">Premium</option>
              </select>
              <button
                onClick={() => toggleAdmin(u.id)}
                style={{
                  padding: '4px 10px', borderRadius: 4, fontSize: '0.7rem', fontWeight: 500, border: 'none',
                  background: u.is_admin ? '#5271ff' : '#27272a', color: u.is_admin ? 'white' : '#71717a',
                }}
              >
                {u.is_admin ? 'Admin' : 'User'}
              </button>
            </div>
          </div>
          {u.targets && u.targets.length > 0 && (
            <div style={{ paddingLeft: 12 }}>
              {u.targets.map((t) => (
                <div key={t.id}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0', fontSize: '0.75rem' }}>
                    <span style={{ color: '#a1a1aa' }}>{t.name} <span style={{ color: '#3f3f46' }}>({t.type})</span></span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span style={{ color: '#52525b' }}>{t.tweets} tweets ({t.analyzed} analyses)</span>
                      <button
                        onClick={() => viewTweets(t.id, t.name)}
                        style={{
                          padding: '3px 8px', borderRadius: 4, fontSize: '0.68rem',
                          background: selectedTarget === t.id ? '#5271ff' : '#18181b',
                          color: selectedTarget === t.id ? 'white' : '#71717a',
                          border: '1px solid #27272a', cursor: 'pointer',
                        }}
                      >
                        {selectedTarget === t.id ? 'Fermer' : 'Voir tweets'}
                      </button>
                    </div>
                  </div>
                  {selectedTarget === t.id && (
                    <div style={{ marginTop: 8, marginBottom: 12, marginLeft: 8, padding: 12, background: '#09090b', borderRadius: 8, border: '1px solid #1c1c22' }}>
                      {loadingTweets ? (
                        <p style={{ color: '#52525b', fontSize: '0.75rem' }}>Chargement...</p>
                      ) : tweets.length === 0 ? (
                        <p style={{ color: '#52525b', fontSize: '0.75rem' }}>Aucun tweet</p>
                      ) : (
                        <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                          {tweets.map((tw, i) => (
                            <div key={i} style={{ marginBottom: 10, paddingBottom: 8, borderBottom: '1px solid #1c1c22' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                                <span style={{ color: '#e4e4e7', fontSize: '0.72rem', fontWeight: 500 }}>@{tw.author_username || '?'}</span>
                                <div style={{ display: 'flex', gap: 6 }}>
                                  {tw.sentiment && (
                                    <span style={{
                                      padding: '1px 6px', borderRadius: 3, fontSize: '0.65rem', fontWeight: 500,
                                      background: tw.sentiment === 'joie' || tw.sentiment === 'amour' ? 'rgba(52,211,153,0.1)' :
                                                  tw.sentiment === 'colere' || tw.sentiment === 'tristesse' ? 'rgba(248,113,113,0.1)' : 'rgba(82,113,255,0.1)',
                                      color: tw.sentiment === 'joie' || tw.sentiment === 'amour' ? '#34d399' :
                                             tw.sentiment === 'colere' || tw.sentiment === 'tristesse' ? '#f87171' : '#5271ff',
                                    }}>
                                      {tw.sentiment} {tw.confidence ? `(${(tw.confidence * 100).toFixed(0)}%)` : ''}
                                    </span>
                                  )}
                                </div>
                              </div>
                              <p style={{ color: '#a1a1aa', fontSize: '0.72rem', lineHeight: 1.4 }}>
                                {tw.text?.slice(0, 200)}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function TicketsAdmin() {
  const [tickets, setTickets] = useState([]);
  const [filter, setFilter] = useState('open');
  const [responses, setResponses] = useState({});

  const load = () => {
    api.get('/tickets/admin/all', { params: filter ? { status: filter } : {} })
      .then((r) => setTickets(r.data || []))
      .catch(() => {});
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter]);

  const respond = async (id) => {
    const text = responses[id];
    if (!text || text.trim().length === 0) return;
    try {
      await api.post(`/tickets/admin/${id}/respond`, { admin_response: text, status: 'closed' });
      setResponses((r) => ({ ...r, [id]: '' }));
      load();
    } catch (err) { /* ignore */ }
  };

  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        {['open', 'in_progress', 'closed', ''].map((s) => (
          <button key={s || 'all'} onClick={() => setFilter(s)}
            style={{
              padding: '4px 10px', borderRadius: 4, fontSize: '0.72rem', cursor: 'pointer',
              background: filter === s ? '#5271ff' : '#18181b', color: filter === s ? 'white' : '#71717a',
              border: '1px solid #27272a',
            }}>
            {s === '' ? 'Tous' : s === 'open' ? 'Ouverts' : s === 'in_progress' ? 'En cours' : 'Résolus'}
          </button>
        ))}
      </div>
      {tickets.length === 0 ? (
        <p style={{ color: '#52525b', fontSize: '0.82rem' }}>Aucun ticket.</p>
      ) : (
        tickets.map((t) => (
          <div key={t.id} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: '1px solid #1c1c22' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: '#e4e4e7', fontSize: '0.85rem', fontWeight: 500 }}>{t.subject}</span>
              <span style={{ color: '#71717a', fontSize: '0.7rem' }}>{t.user || 'anonyme'} · {t.category} · {t.status}</span>
            </div>
            <p style={{ color: '#a1a1aa', fontSize: '0.8rem', margin: '6px 0' }}>{t.message}</p>
            {t.admin_response ? (
              <p style={{ color: '#34d399', fontSize: '0.78rem' }}>Réponse : {t.admin_response}</p>
            ) : (
              <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                <input
                  type="text" placeholder="Répondre..." value={responses[t.id] || ''}
                  onChange={(e) => setResponses((r) => ({ ...r, [t.id]: e.target.value }))}
                  style={{ flex: 1, padding: '6px 8px', background: '#09090b', border: '1px solid #27272a', borderRadius: 6, color: '#e4e4e7', fontSize: '0.78rem' }}
                />
                <button onClick={() => respond(t.id)}
                  style={{ padding: '6px 12px', background: '#5271ff', border: 'none', borderRadius: 6, color: 'white', fontSize: '0.75rem', cursor: 'pointer' }}>
                  Répondre & clore
                </button>
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}

function QuestionLogs() {
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    api.get('/admin/question-logs', { params: { limit: 100 } })
      .then((r) => setLogs(r.data || []))
      .catch(() => {});
  }, []);

  if (!logs.length) return <p style={{ color: '#52525b', fontSize: '0.82rem' }}>Aucune question loggée.</p>;

  return (
    <div style={{ maxHeight: 400, overflowY: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.76rem' }}>
        <thead>
          <tr style={{ color: '#52525b', textAlign: 'left' }}>
            <th style={{ padding: '6px 8px' }}>Question</th>
            <th style={{ padding: '6px 8px' }}>Intent</th>
            <th style={{ padding: '6px 8px' }}>Mode</th>
            <th style={{ padding: '6px 8px' }}>Temps</th>
            <th style={{ padding: '6px 8px' }}>Date</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((q) => (
            <tr key={q.id} style={{ borderTop: '1px solid #1c1c22', color: '#a1a1aa' }}>
              <td style={{ padding: '6px 8px', maxWidth: 280 }}>{q.question}</td>
              <td style={{ padding: '6px 8px', color: '#5271ff' }}>{q.intent_detected || '-'}</td>
              <td style={{ padding: '6px 8px' }}>{q.mode_used || '-'}</td>
              <td style={{ padding: '6px 8px' }}>{q.response_time_ms ? `${q.response_time_ms}ms` : '-'}</td>
              <td style={{ padding: '6px 8px', color: '#52525b' }}>{q.created_at?.slice(0, 16)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
