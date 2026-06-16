import React, { useEffect, useRef, useState } from 'react';
import { ragChat, ragInfo, ragIndex, ragMcpTools } from '../services/api';

export default function RagChat() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        "Salut ! Je suis le RAG SentiFlow (from scratch + MCP).\n\nPose-moi une question sur les sentiments Twitter.\nSi je n'ai pas les données en base, j'irai les chercher en temps réel sur Twitter via le MCP.\n\nExemple : \"Quel est le sentiment sur #france ?\"",
    },
  ]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [ragStatus, setRagStatus] = useState(null);
  const [mcpTools, setMcpTools] = useState([]);
  const bottomRef = useRef(null);

  useEffect(() => {
    ragInfo().then((r) => setRagStatus(r.data)).catch(() => {});
    ragMcpTools().then((r) => setMcpTools(r.data?.tools || [])).catch(() => {});
  }, []);

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
      const response = await ragChat({ question: q, enable_mcp: true });
      const data = response.data;

      const meta = [
        `📊 **${data.total_retrieved}** tweets récupérés`,
        `🤖 Générateur : ${data.generator}`,
        data.mcp_used ? `🐦 MCP Twitter utilisé (${data.mcp_tweets_fetched} tweets temps réel)` : '💾 Données depuis la base',
        `⏱ Temps : ${data.metrics?.timing?.total?.toFixed(2)}s`,
      ].join('\n');

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.answer || "Pas de réponse.",
          meta,
          sources: data.sources,
          metrics: data.metrics,
          mcpUsed: data.mcp_used,
        },
      ]);
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message || 'Erreur inconnue';
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `❌ Erreur : ${detail}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleIndex = async () => {
    setLoading(true);
    try {
      const r = await ragIndex({ days: 30 });
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `📚 Index reconstruit : ${r.data.indexed} tweets indexés, vocab=${r.data.vocab_size}` },
      ]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'assistant', content: '❌ Erreur indexation' }]);
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
    <div style={{ maxWidth: 980, margin: '0 auto', height: 'calc(100vh - 60px)', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <h1 style={{ marginBottom: 6 }}>🔍 RAG SentiFlow (From Scratch + MCP)</h1>
        <p style={{ color: '#9ca3af', margin: 0 }}>
          Retrieval-Augmented Generation : TF-IDF + BM25 + co-occurrences dynamiques + re-ranking + Groq LLaMA 3
        </p>
        {ragStatus && (
          <div style={{ color: '#6b7280', fontSize: 12, marginTop: 6 }}>
            Index : {ragStatus.index?.indexed_count || 0} tweets | Vocab : {ragStatus.index?.vocab_size || 0} |
            MCP : {mcpTools.length} outils disponibles
          </div>
        )}
      </div>

      {/* Messages */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          border: '1px solid #2a2f3a',
          borderRadius: 14,
          padding: 16,
          background: '#0f141c',
          marginBottom: 14,
        }}
      >
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              marginBottom: 12,
            }}
          >
            <div
              style={{
                maxWidth: '80%',
                padding: '12px 14px',
                borderRadius: 14,
                whiteSpace: 'pre-line',
                background: msg.role === 'user' ? '#2563eb' : '#1f2937',
                color: 'white',
                lineHeight: 1.5,
              }}
            >
              {msg.content}

              {msg.meta && (
                <div style={{ marginTop: 12, padding: '8px 10px', background: '#111827', borderRadius: 8, fontSize: 12, color: '#9ca3af' }}>
                  {msg.meta}
                </div>
              )}

              {msg.sources && msg.sources.length > 0 && (
                <details style={{ marginTop: 10, color: '#d1d5db' }}>
                  <summary style={{ cursor: 'pointer', fontSize: 12 }}>📋 Sources ({msg.sources.length} tweets)</summary>
                  <div style={{ fontSize: 11, marginTop: 6 }}>
                    {msg.sources.map((s, j) => (
                      <div key={j} style={{ marginBottom: 6, padding: '4px 6px', background: '#111827', borderRadius: 6 }}>
                        <strong>@{s.author}</strong> [{s.target}] → {s.sentiment} ({(s.confidence * 100).toFixed(0)}%)
                        <br />
                        <span style={{ color: '#6b7280' }}>{s.text?.slice(0, 120)}...</span>
                      </div>
                    ))}
                  </div>
                </details>
              )}

              {msg.metrics && (
                <details style={{ marginTop: 8, color: '#d1d5db' }}>
                  <summary style={{ cursor: 'pointer', fontSize: 12 }}>📈 Métriques RAG</summary>
                  <pre style={{ fontSize: 10, marginTop: 4 }}>
                    {JSON.stringify(msg.metrics, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ color: '#9ca3af', marginTop: 8 }}>
            🔄 Recherche en cours (TF-IDF + BM25 + MCP si nécessaire)...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: 10 }}>
        <button
          onClick={handleIndex}
          disabled={loading}
          title="Reconstruire l'index RAG depuis la BDD"
          style={{
            borderRadius: 12,
            padding: '0 14px',
            cursor: loading ? 'not-allowed' : 'pointer',
            background: '#374151',
            color: 'white',
            border: 'none',
            fontSize: 18,
          }}
        >
          📚
        </button>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Pose une question (ex: Quel est le sentiment sur #france ?)"
          rows={2}
          style={{
            flex: 1,
            resize: 'none',
            borderRadius: 12,
            padding: 12,
            background: '#111827',
            color: 'white',
            border: '1px solid #374151',
            outline: 'none',
          }}
        />
        <button
          onClick={handleAsk}
          disabled={loading}
          style={{
            borderRadius: 12,
            padding: '0 22px',
            cursor: loading ? 'not-allowed' : 'pointer',
            background: loading ? '#4b5563' : '#10b981',
            color: 'white',
            border: 'none',
            fontWeight: 700,
          }}
        >
          Envoyer
        </button>
      </div>
    </div>
  );
}
