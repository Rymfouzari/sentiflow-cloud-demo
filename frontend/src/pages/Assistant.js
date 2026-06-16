import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { assistantChat } from '../services/api';
import { Send, Loader2, ExternalLink, ChevronDown, Download, FileText, RefreshCw } from 'lucide-react';
import api from '../services/api';

function formatMeta(data) {
  if (!data) return null;
  const parts = [];
  if (data.total_retrieved) parts.push(`${data.total_retrieved} tweets`);
  if (data.generator) parts.push(data.generator.replace(/_/g, ' '));
  if (data.mcp_used) parts.push(`MCP: ${data.mcp_tweets_fetched || 0} temps reel`);
  if (data.metrics?.timing?.total) parts.push(`${data.metrics.timing.total.toFixed(2)}s`);
  return parts.join(' · ');
}

function formatExecutionLog(logs = []) {
  if (!logs || !logs.length) return null;
  return logs.map((step) => {
    const target = step.target || step.target_name || '';
    switch (step.action) {
      case 'create_target': return `Cible creee : ${target}`;
      case 'reuse_target': return `Cible existante : ${target}`;
      case 'collect_tweets': return `Collecte ${target} : ${step.saved || 0} nouveaux, ${step.duplicates || 0} doublons`;
      case 'skip_collect': return `Collecte ${target} : donnees deja disponibles`;
      case 'analyze_sentiments': return `Analyse ${target} : ${step.analyzed || 0} tweets`;
      case 'skip_analyze': return `Analyse ${target} : rien de nouveau`;
      default: return `${step.action || 'action'} ${target}`;
    }
  }).join('\n');
}

function SourcesList({ sources }) {
  if (!sources || !sources.length) return null;
  return (
    <details style={{ marginTop: 12, color: '#71717a' }}>
      <summary style={{ cursor: 'pointer', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: 4 }}>
        <ChevronDown size={12} /> {sources.length} source(s)
      </summary>
      <div style={{ marginTop: 8 }}>
        {sources.slice(0, 5).map((s, i) => (
          <div key={i} style={{
            padding: '8px 10px',
            background: '#09090b',
            borderRadius: 6,
            marginBottom: 4,
            fontSize: '0.73rem',
            color: '#a1a1aa',
            border: '1px solid #1c1c22',
          }}>
            <span style={{ color: '#e4e4e7' }}>@{s.author}</span>
            <span style={{ margin: '0 6px', color: '#3f3f46' }}>·</span>
            <span style={{ color: '#5271ff' }}>{s.sentiment}</span> ({(s.confidence * 100).toFixed(0)}%)
            <div style={{ marginTop: 3, color: '#52525b', lineHeight: 1.4 }}>
              {s.text?.slice(0, 120)}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

function ExportPdfButton({ message }) {
  const [loading, setLoading] = useState(false);

  const handleExport = async () => {
    setLoading(true);
    try {
      let res;
      if (message.dashboardId) {
        // Rapport "dashboard de tweets" complet (à partir du dashboard sauvegardé)
        res = await api.get(`/dashboards/${message.dashboardId}/pdf`, { responseType: 'blob' });
      } else {
        // Fallback : rapport à partir des sources de la réponse
        res = await api.post('/assistant/export-pdf', {
          question: message.originalQuestion || '',
          answer: message.content || '',
          sources: message.sources || [],
          metrics: message.metrics || null,
        }, { responseType: 'blob' });
      }

      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'sentiflow_rapport.pdf';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export PDF failed:', err);
    } finally {
      setLoading(false);
    }
  };

  if (!message.sources || !message.sources.length) return null;

  return (
    <button onClick={handleExport} disabled={loading} style={{
      marginTop: 8,
      padding: '6px 10px',
      background: 'transparent',
      border: '1px solid #27272a',
      borderRadius: 6,
      color: '#71717a',
      fontSize: '0.72rem',
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      cursor: loading ? 'wait' : 'pointer',
    }}>
      {loading ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <FileText size={12} />}
      Exporter le dashboard PDF
    </button>
  );
}

export default function Assistant() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        "Bienvenue sur l'assistant SentiFlow.\n\nJe fonctionne en 3 modes selon ta question :\n\n" +
        "MODE AGENT (collecte + analyse + dashboard) :\n" +
        "• \"Recupere les tweets de #bts\"\n" +
        "• \"Cree la cible @elonmusk et analyse\"\n" +
        "• \"Collecte #minecraft et compare avec #fortnite\"\n\n" +
        "MODE RAG (recherche dans les tweets existants) :\n" +
        "• \"Quel est le sentiment sur #france ?\"\n" +
        "• \"Pourquoi les gens sont en colere sur #politique ?\"\n" +
        "• \"Compare les sentiments de #psg et #om\"\n\n" +
        "MODE BDD (stats directes) :\n" +
        "• \"Combien de tweets en base ?\"\n" +
        "• \"Quelles sont mes cibles ?\"\n" +
        "• \"Repartition des langues\"",
    },
  ]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleAsk = async () => {
    const q = question.trim();
    if (!q || loading) return;

    setMessages((prev) => [...prev, { role: 'user', content: q }]);
    setQuestion('');
    setLoading(true);

    try {
      const response = await assistantChat({ question: q, enable_mcp: true });
      const data = response.data;

      // Détecter si la réponse indique pas assez de données
      const answer = data.answer || "Pas de reponse disponible.";
      const noData = answer.toLowerCase().includes("pas de tweet") ||
                     answer.toLowerCase().includes("pas assez de") ||
                     answer.toLowerCase().includes("aucun tweet") ||
                     answer.toLowerCase().includes("pas de données") ||
                     answer.toLowerCase().includes("pas trouvé") ||
                     (data.total_retrieved === 0);

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: noData
            ? answer + "\n\nJe peux collecter de nouveaux tweets pour cette cible si tu veux."
            : answer,
          meta: formatMeta(data),
          sources: data.sources,
          metrics: data.metrics,
          executionLog: formatExecutionLog(data.execution_log),
          dashboardId: data.dashboard_id,
          dashboardUrl: data.dashboard_url,
          plan: data.plan,
          mode: data.mode,
          originalQuestion: q,
          canCollect: noData,
        },
      ]);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : (Array.isArray(detail) ? detail.map(d => d.msg).join(', ') : JSON.stringify(detail || err.message));
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Erreur : ${msg}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleCollectAndRetry = async (msg) => {
    if (loading) return;
    setLoading(true);
    setMessages((prev) => [...prev, { role: 'user', content: `Collecte et reanalyse : ${msg.originalQuestion}` }]);

    try {
      // Forcer le mode agent pour collecter
      const response = await assistantChat({
        question: `recupere les tweets et ${msg.originalQuestion}`,
        enable_mcp: true,
        force_mode: 'agent',
      });
      const data = response.data;
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.answer || "Voici les resultats apres collecte.",
          meta: formatMeta(data),
          sources: data.sources,
          metrics: data.metrics,
          executionLog: formatExecutionLog(data.execution_log),
          dashboardId: data.dashboard_id,
          dashboardUrl: data.dashboard_url,
          plan: data.plan,
          mode: data.mode,
          originalQuestion: msg.originalQuestion,
        },
      ]);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setMessages((prev) => [...prev, { role: 'assistant', content: `Erreur collecte : ${detail || err.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerate = async (msg) => {
    if (loading) return;
    const feedback = window.prompt("Qu'est-ce qui ne va pas ? (ex: mauvaise cible, reponse vague...)");
    if (!feedback) return;

    setLoading(true);
    try {
      const response = await api.post('/assistant/feedback', {
        question: msg.originalQuestion,
        previous_answer: msg.content,
        feedback: feedback,
        regenerate_mode: 'auto',
      }, { timeout: 240000 });

      const data = response.data;
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.answer || "Reponse regeneree indisponible.",
          meta: `Regenere (${data.mode}) | Feedback: ${data.feedback_applied}`,
          sources: data.sources,
          originalQuestion: msg.originalQuestion,
          mode: data.mode,
        },
      ]);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setMessages((prev) => [...prev, { role: 'assistant', content: `Erreur regeneration : ${detail || err.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  };

  return (
    <div className="animate-in" style={{ maxWidth: 880, margin: '0 auto', height: 'calc(100vh - 72px)', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1 style={{ marginBottom: 4, fontSize: '1.4rem' }}>Assistant IA</h1>
          <p style={{ color: '#52525b', fontSize: '0.82rem' }}>
            RAG from scratch + Groq LLaMA 3
          </p>
        </div>
        <Link to="/dashboards/generated" style={{ fontSize: '0.8rem', color: '#5271ff', display: 'flex', alignItems: 'center', gap: 4 }}>
          Mes rapports IA <ExternalLink size={12} />
        </Link>
      </div>

      {/* Messages */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        borderRadius: 12,
        padding: 18,
        background: '#0f0f12',
        border: '1px solid #1c1c22',
        marginBottom: 14,
      }}>
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              marginBottom: 16,
            }}
          >
            <div style={{
              maxWidth: '80%',
              padding: '14px 16px',
              borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
              whiteSpace: 'pre-line',
              background: msg.role === 'user' ? '#5271ff' : '#18181b',
              color: msg.role === 'user' ? 'white' : '#e4e4e7',
              lineHeight: 1.55,
              fontSize: '0.88rem',
              border: msg.role === 'user' ? 'none' : '1px solid #27272a',
            }}>
              {msg.content}

              {/* Dashboard link */}
              {msg.dashboardUrl && (
                <Link
                  to={msg.dashboardUrl}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    marginTop: 12, padding: '8px 14px', borderRadius: 6,
                    background: '#5271ff', color: 'white', fontSize: '0.8rem', fontWeight: 600,
                  }}
                >
                  Voir le dashboard <ExternalLink size={13} />
                </Link>
              )}

              {/* Meta info */}
              {msg.meta && (
                <div style={{
                  marginTop: 10, padding: '6px 10px', background: '#09090b',
                  borderRadius: 5, fontSize: '0.72rem', color: '#52525b', border: '1px solid #1c1c22',
                }}>
                  {msg.mode && (
                    <span style={{
                      display: 'inline-block',
                      padding: '2px 6px',
                      borderRadius: 3,
                      marginRight: 8,
                      fontSize: '0.68rem',
                      fontWeight: 600,
                      background: msg.mode === 'agent' ? 'rgba(52,211,153,0.1)' : msg.mode === 'database' ? 'rgba(251,191,36,0.1)' : 'rgba(82,113,255,0.1)',
                      color: msg.mode === 'agent' ? '#34d399' : msg.mode === 'database' ? '#fbbf24' : '#5271ff',
                      border: `1px solid ${msg.mode === 'agent' ? 'rgba(52,211,153,0.2)' : msg.mode === 'database' ? 'rgba(251,191,36,0.2)' : 'rgba(82,113,255,0.2)'}`,
                    }}>
                      {msg.mode === 'agent' ? 'AGENT — Collecte + Analyse + Dashboard' : msg.mode === 'database' ? 'BDD — Interrogation directe' : 'RAG — Recherche + Generation'}
                    </span>
                  )}
                  {msg.meta}
                </div>
              )}

              {/* Export PDF + Feedback + Collect */}
              {msg.originalQuestion && (
                <div style={{ display: 'flex', gap: 6, marginTop: 10, flexWrap: 'wrap' }}>
                  <ExportPdfButton message={msg} />
                  {msg.role === 'assistant' && (
                    <button
                      onClick={() => handleRegenerate(msg)}
                      disabled={loading}
                      style={{
                        padding: '6px 10px', background: 'transparent',
                        border: '1px solid #27272a', borderRadius: 6,
                        color: '#71717a', fontSize: '0.72rem',
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        cursor: loading ? 'not-allowed' : 'pointer',
                      }}
                    >
                      <RefreshCw size={12} /> Pas satisfait
                    </button>
                  )}
                  {msg.canCollect && (
                    <button
                      onClick={() => handleCollectAndRetry(msg)}
                      disabled={loading}
                      style={{
                        padding: '6px 10px', background: 'rgba(82,113,255,0.1)',
                        border: '1px solid rgba(82,113,255,0.2)', borderRadius: 6,
                        color: '#5271ff', fontSize: '0.72rem',
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        cursor: loading ? 'not-allowed' : 'pointer',
                      }}
                    >
                      <Send size={12} /> Collecter et reessayer
                    </button>
                  )}
                </div>
              )}

              {/* Sources */}
              <SourcesList sources={msg.sources} />

              {/* Execution log */}
              {msg.executionLog && (
                <details style={{ marginTop: 8, color: '#52525b' }}>
                  <summary style={{ cursor: 'pointer', fontSize: '0.72rem', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <ChevronDown size={11} /> Actions
                  </summary>
                  <pre style={{ fontSize: '0.7rem', marginTop: 4, whiteSpace: 'pre-wrap', color: '#3f3f46' }}>
                    {msg.executionLog}
                  </pre>
                </details>
              )}

              {/* Plan */}
              {msg.plan && (
                <details style={{ marginTop: 6, color: '#52525b' }}>
                  <summary style={{ cursor: 'pointer', fontSize: '0.72rem', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <ChevronDown size={11} /> Plan LLM
                  </summary>
                  <pre style={{ fontSize: '0.68rem', marginTop: 4, color: '#3f3f46' }}>
                    {JSON.stringify(msg.plan, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#52525b', marginTop: 8, fontSize: '0.84rem' }}>
            <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
            Analyse en cours...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: 10 }}>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Pose une question... (ex: Quel est le sentiment sur #france ?)"
          rows={2}
          style={{
            flex: 1, resize: 'none', borderRadius: 10, padding: '12px 14px',
            background: '#0f0f12', color: '#fafafa', border: '1px solid #1c1c22',
            outline: 'none', fontSize: '0.88rem', lineHeight: 1.5,
            transition: 'border-color 0.15s',
          }}
          onFocus={(e) => e.target.style.borderColor = '#5271ff'}
          onBlur={(e) => e.target.style.borderColor = '#1c1c22'}
        />
        <button
          onClick={handleAsk}
          disabled={loading}
          className="btn-primary"
          style={{ borderRadius: 10, padding: '0 20px', opacity: loading ? 0.5 : 1 }}
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
