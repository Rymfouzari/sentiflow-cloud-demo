import React, { useState, useRef, useEffect } from 'react';
import { ragChat, ragIndex } from '../services/api';
import './Chatbot.css';

export default function Chatbot() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([
    { role: 'bot', text: 'Salut ! Je suis l\'assistant SentiFlow. Pose-moi une question sur les sentiments des tweets.' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [indexed, setIndexed] = useState(false);
  const messagesEnd = useRef(null);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleIndex = async () => {
    setLoading(true);
    setMessages(m => [...m, { role: 'bot', text: '⏳ Indexation des tweets en cours...' }]);
    try {
      const res = await ragIndex();
      setMessages(m => [...m, { role: 'bot', text: `✅ ${res.data.indexed} tweets indexés pour la recherche.` }]);
      setIndexed(true);
    } catch (err) {
      setMessages(m => [...m, { role: 'bot', text: '❌ Erreur lors de l\'indexation.' }]);
    }
    setLoading(false);
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const question = input.trim();
    setInput('');
    setMessages(m => [...m, { role: 'user', text: question }]);
    setLoading(true);

    try {
      const res = await ragChat(question);
      const data = res.data;

      let botMsg = data.answer;

      if (data.sources && data.sources.length > 0) {
        botMsg += '\n\n📎 Sources:';
        data.sources.slice(0, 3).forEach((s, i) => {
          botMsg += `\n${i + 1}. @${s.author || '?'} [${s.sentiment}] "${s.text.slice(0, 80)}..."`;
        });
      }

      if (data.metrics) {
        const m = data.metrics;
        botMsg += `\n\n📊 ${m.retrieval.total_retrieved} tweets trouvés | `;
        botMsg += `Pertinence: ${(m.retrieval.relevance * 100).toFixed(0)}% | `;
        botMsg += `Temps: ${m.timing.total}s`;
      }

      setMessages(m => [...m, { role: 'bot', text: botMsg }]);
    } catch (err) {
      setMessages(m => [...m, { role: 'bot', text: '❌ Erreur: ' + (err.response?.data?.detail || err.message) }]);
    }
    setLoading(false);
  };

  return (
    <>
      <button className="chatbot-toggle" onClick={() => setOpen(!open)}>
        {open ? '✕' : '💬'}
      </button>

      {open && (
        <div className="chatbot-window">
          <div className="chatbot-header">
            <span>🤖 SentiFlow RAG</span>
            {!indexed && (
              <button className="index-btn" onClick={handleIndex} disabled={loading}>
                📥 Indexer
              </button>
            )}
          </div>

          <div className="chatbot-messages">
            {messages.map((msg, i) => (
              <div key={i} className={`chatbot-msg ${msg.role}`}>
                <pre>{msg.text}</pre>
              </div>
            ))}
            {loading && <div className="chatbot-msg bot"><pre>⏳ Réflexion...</pre></div>}
            <div ref={messagesEnd} />
          </div>

          <form className="chatbot-input" onSubmit={handleSend}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Pose une question..."
              disabled={loading}
            />
            <button type="submit" disabled={loading || !input.trim()}>➤</button>
          </form>
        </div>
      )}
    </>
  );
}
