import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { askLlmAgent, getLlmModelInfo, sendLlmFeedback } from '../services/api';

function formatExecutionLog(logs = []) {
  if (!logs.length) return '';

  return logs
    .map((step) => {
      const target = step.target || step.target_name || '';
      switch (step.action) {
        case 'create_target':
          return `✅ Cible créée : ${target}`;
        case 'reuse_target':
          return `♻️ Cible déjà existante : ${target}`;
        case 'collect_tweets':
          return `📥 Collecte ${target} : ${step.saved || 0} nouveaux tweets, ${step.duplicates || 0} doublons`;
        case 'skip_collect':
          return `⏭️ Collecte ${target} non relancée : données déjà disponibles`;
        case 'analyze_sentiments':
          return `🤖 Analyse ${target} : ${step.analyzed || 0} tweets analysés`;
        case 'skip_analyze':
          return `⏭️ Analyse ${target} ignorée : aucun nouveau tweet à analyser`;
        default:
          return `• ${step.action || 'action'} ${target}`;
      }
    })
    .join('\n');
}

function cleanAnswer(answer = '') {
  // Le backend met un récap technique avant la réponse. Dans le chat on garde
  // l'expérience propre : la partie technique reste disponible dans un détail.
  const marker = '\n\n###';
  const markerIndex = answer.indexOf(marker);
  if (answer.startsWith('Actions effectuées :') && markerIndex !== -1) {
    return answer.slice(markerIndex + 2).trim();
  }

  const altMarker = '\n\nSynthèse';
  const altIndex = answer.indexOf(altMarker);
  if (answer.startsWith('Actions effectuées :') && altIndex !== -1) {
    return answer.slice(altIndex + 2).trim();
  }

  return answer;
}


function extractTargetIdsFromAgentResponse(data = {}) {
  const ids = new Set();

  (data.targets || []).forEach((target) => {
    const id = target?.target_id || target?.id;
    if (id) ids.add(id);
  });

  (data.execution_log || []).forEach((step) => {
    if (step?.target_id) ids.add(step.target_id);
  });

  (data.dashboard_config?.target_ids || []).forEach((id) => {
    if (id) ids.add(id);
  });

  return Array.from(ids);
}

function formatApiError(err, fallback) {
  const detail = err?.response?.data?.detail || err?.response?.data?.message;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || JSON.stringify(item))
      .join('\n');
  }
  if (detail && typeof detail === 'object') {
    return JSON.stringify(detail, null, 2);
  }
  return detail || err?.message || fallback;
}

function DashboardButton({ dashboardId, dashboardUrl }) {
  const url = dashboardUrl || (dashboardId ? `/dashboards/generated/${dashboardId}` : null);
  if (!url) return null;

  return (
    <div style={{ marginTop: 12 }}>
      <Link
        to={url}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '10px 14px',
          borderRadius: 10,
          background: '#ef4444',
          color: 'white',
          textDecoration: 'none',
          fontWeight: 700,
        }}
      >
        Afficher le dashboard
      </Link>
    </div>
  );
}


function LlmFeedbackButtons({ message, disabled, onRegenerate }) {
  if (!message.originalQuestion || message.role !== 'assistant') return null;

  return (
    <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onRegenerate(message)}
        style={{
          borderRadius: 8,
          border: '1px solid #4b5563',
          background: '#111827',
          color: 'white',
          padding: '6px 10px',
          cursor: disabled ? 'not-allowed' : 'pointer',
        }}
      >
        🔁 Pas satisfait, régénérer
      </button>
    </div>
  );
}

export default function AssistantLLM() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        "Salut, je peux créer une cible, collecter les tweets, lancer l'analyse de sentiment puis répondre. Exemple : récupère les tweets avec le #france.",
    },
  ]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [modelInfo, setModelInfo] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    getLlmModelInfo()
      .then((response) => setModelInfo(response.data))
      .catch(() => setModelInfo(null));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const pushMessage = (message) => {
    setMessages((current) => [...current, message]);
  };

  const handleAsk = async () => {
    const cleanQuestion = question.trim();
    if (!cleanQuestion || loading) return;

    pushMessage({ role: 'user', content: cleanQuestion });
    setQuestion('');
    setLoading(true);

    try {
      const response = await askLlmAgent({
        question: cleanQuestion,
        generate_dashboard: true,
        allow_auto_collect: true,
        allow_auto_analyze: true,
      });

      const data = response.data;
      const execution = formatExecutionLog(data.execution_log);
      const answer = cleanAnswer(data.answer || "Je n'ai pas réussi à générer une réponse.");

      pushMessage({
        role: 'assistant',
        content: answer,
        execution,
        dashboardId: data.dashboard_id || data.dashboard_config?.saved_dashboard_id,
        dashboardUrl: data.dashboard_url || data.dashboard_config?.dashboard_url,
        plan: data.plan,
        modelInfo: data.model_info,
        originalQuestion: cleanQuestion,
        targetIds: extractTargetIdsFromAgentResponse(data),
      });
    } catch (err) {
      console.error(err);
      pushMessage({
        role: 'assistant',
        content: formatApiError(err, "Erreur pendant l'exécution de l'agent LLM. Regarde les logs de l'API."),
      });
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerateLlm = async (message) => {
    if (loading) return;
    const reason = window.prompt(
      "Qu'est-ce qui ne va pas dans la réponse ? Exemple : mauvaise cible, réponse trop vague, mauvais sentiment...",
      "Réponse pas satisfaisante"
    );
    if (reason === null) return;

    setLoading(true);
    try {
      const response = await sendLlmFeedback({
        question: message.originalQuestion,
        previous_answer: message.content,
        target_ids: message.targetIds || [],
        days: message.plan?.days || 7,
        intent: message.plan?.intent,
        sentiment_filter: message.plan?.sentiment_filter,
        reason,
        regenerate: true,
      });

      const data = response.data.regenerated;
      if (!data) {
        pushMessage({ role: 'assistant', content: 'Feedback enregistré, mais aucune réponse régénérée.' });
        return;
      }

      pushMessage({
        role: 'assistant',
        content: cleanAnswer(data.answer || "Réponse régénérée indisponible."),
        execution: formatExecutionLog(data.execution_log),
        dashboardId: data.dashboard_id || data.dashboard_config?.saved_dashboard_id,
        dashboardUrl: data.dashboard_url || data.dashboard_config?.dashboard_url,
        plan: data.plan || message.plan,
        modelInfo: data.model_info || message.modelInfo,
        originalQuestion: message.originalQuestion,
        targetIds: extractTargetIdsFromAgentResponse(data) || message.targetIds || [],
      });
    } catch (err) {
      console.error(err);
      pushMessage({
        role: 'assistant',
        content: formatApiError(err, "Erreur pendant la régénération LLM."),
      });
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleAsk();
    }
  };

  return (
    <div style={{ maxWidth: 980, margin: '0 auto', height: 'calc(100vh - 60px)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ marginBottom: 16 }}>
        <h1 style={{ marginBottom: 6 }}>Assistant LLM SentiFlow</h1>
        <p style={{ color: '#9ca3af', margin: 0 }}>
          Agent local : crée les cibles manquantes, collecte, analyse les nouveaux tweets et répond sur les données disponibles.
        </p>
        {modelInfo && (
          <p style={{ color: '#6b7280', fontSize: 12, marginTop: 6 }}>
            LLM : {modelInfo.type} — checkpoint chargé : {modelInfo.checkpoint_loaded ? 'oui' : 'non, fallback actif'}
          </p>
        )}
      </div>

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
        {messages.map((message, index) => (
          <div
            key={index}
            style={{
              display: 'flex',
              justifyContent: message.role === 'user' ? 'flex-end' : 'flex-start',
              marginBottom: 12,
            }}
          >
            <div
              style={{
                maxWidth: '78%',
                padding: '12px 14px',
                borderRadius: 14,
                whiteSpace: 'pre-line',
                background: message.role === 'user' ? '#2563eb' : '#1f2937',
                color: 'white',
                lineHeight: 1.45,
              }}
            >
              {message.content}

              <DashboardButton dashboardId={message.dashboardId} dashboardUrl={message.dashboardUrl} />

              <LlmFeedbackButtons
                message={message}
                disabled={loading}
                onRegenerate={handleRegenerateLlm}
              />

              {message.execution && (
                <details style={{ marginTop: 12, color: '#d1d5db' }}>
                  <summary style={{ cursor: 'pointer' }}>Voir les actions techniques</summary>
                  <pre style={{ overflowX: 'auto', fontSize: 12, whiteSpace: 'pre-wrap' }}>
                    {message.execution}
                  </pre>
                </details>
              )}

              {message.plan && (
                <details style={{ marginTop: 12, color: '#d1d5db' }}>
                  <summary style={{ cursor: 'pointer' }}>Voir le plan LLM</summary>
                  <pre style={{ overflowX: 'auto', fontSize: 12 }}>
                    {JSON.stringify(message.plan, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ color: '#9ca3af', marginTop: 8 }}>
            Agent en cours : planification → cible → collecte → analyse → réponse...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div style={{ display: 'flex', gap: 10 }}>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ex : récupère les tweets avec le #france / compare #france et #minecraft / analyse en profondeur #love"
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
            background: loading ? '#4b5563' : '#ef4444',
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
