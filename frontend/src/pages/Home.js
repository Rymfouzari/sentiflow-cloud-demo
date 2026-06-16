import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ArrowRight, ChevronLeft, ChevronRight, Zap, Brain, Search, BarChart3, Shield, Globe } from 'lucide-react';

const SLIDES = [
  {
    title: "Analyse de sentiments en temps reel",
    description: "SentiFlow collecte et analyse les tweets pour detecter les emotions : joie, colere, tristesse, peur, surprise, amour.",
    gradient: "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
    icon: <Zap size={40} color="#5271ff" />,
  },
  {
    title: "RAG From Scratch",
    description: "Notre moteur de recherche utilise TF-IDF, BM25, et Reciprocal Rank Fusion — entierement code a la main, sans librairie externe.",
    gradient: "linear-gradient(135deg, #0f2027 0%, #203a43 100%)",
    icon: <Search size={40} color="#5271ff" />,
  },
  {
    title: "LLM Planner + Groq",
    description: "Un Transformer decoder-only (TinyGPT) comprend vos questions. Groq LLaMA 3 genere des reponses naturelles a partir des donnees.",
    gradient: "linear-gradient(135deg, #1a1a2e 0%, #2d1b69 100%)",
    icon: <Brain size={40} color="#5271ff" />,
  },
  {
    title: "Dashboards automatiques",
    description: "Chaque analyse genere un dashboard interactif avec graphiques, tendances, et mots-cles. Exportable en PDF.",
    gradient: "linear-gradient(135deg, #0f2027 0%, #2c5364 100%)",
    icon: <BarChart3 size={40} color="#5271ff" />,
  },
];

const FEATURES = [
  { icon: <Search size={24} />, title: "Retrieval From Scratch", desc: "TF-IDF + BM25 + RRF + Re-ranking code main. Pas de librairie externe." },
  { icon: <Brain size={24} />, title: "TinyGPT Planner", desc: "Transformer decoder-only entraine sur 8000+ exemples pour comprendre vos intentions." },
  { icon: <Zap size={24} />, title: "Groq LLaMA 3", desc: "Generation de reponses naturelles via l'API Groq. Rapide et precis." },
  { icon: <Globe size={24} />, title: "MCP Twitter", desc: "Recherche en temps reel si les donnees locales sont insuffisantes." },
  { icon: <BarChart3 size={24} />, title: "Dashboards IA", desc: "Graphiques generes automatiquement : repartition, tendance, comparaison." },
  { icon: <Shield size={24} />, title: "Feedback Loop", desc: "Corrigez les resultats. Le modele se re-entraine tous les 2 jours." },
];

function Carousel() {
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setCurrent((c) => (c + 1) % SLIDES.length), 5000);
    return () => clearInterval(timer);
  }, []);

  const slide = SLIDES[current];

  return (
    <div style={{ position: 'relative', borderRadius: 16, overflow: 'hidden', marginBottom: 48 }}>
      <div style={{
        background: slide.gradient,
        padding: '60px 48px',
        minHeight: 280,
        display: 'flex',
        alignItems: 'center',
        gap: 40,
        transition: 'all 0.4s ease',
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ marginBottom: 20 }}>{slide.icon}</div>
          <h2 style={{ fontSize: '1.6rem', marginBottom: 12, color: '#fafafa' }}>{slide.title}</h2>
          <p style={{ color: '#a1a1aa', fontSize: '1rem', lineHeight: 1.7, maxWidth: 500 }}>{slide.description}</p>
        </div>
      </div>

      {/* Navigation */}
      <div style={{ position: 'absolute', bottom: 20, left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: 8 }}>
        {SLIDES.map((_, i) => (
          <button
            key={i}
            onClick={() => setCurrent(i)}
            style={{
              width: i === current ? 24 : 8,
              height: 8,
              borderRadius: 4,
              border: 'none',
              background: i === current ? '#5271ff' : '#3f3f46',
              transition: 'all 0.3s',
            }}
          />
        ))}
      </div>

      <button onClick={() => setCurrent((c) => (c - 1 + SLIDES.length) % SLIDES.length)}
        style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)', background: 'rgba(0,0,0,0.5)', border: 'none', borderRadius: '50%', width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white' }}>
        <ChevronLeft size={20} />
      </button>
      <button onClick={() => setCurrent((c) => (c + 1) % SLIDES.length)}
        style={{ position: 'absolute', right: 16, top: '50%', transform: 'translateY(-50%)', background: 'rgba(0,0,0,0.5)', border: 'none', borderRadius: '50%', width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white' }}>
        <ChevronRight size={20} />
      </button>
    </div>
  );
}

export default function Home() {
  const { user } = useAuth();

  return (
    <div className="animate-in" style={{ maxWidth: 900, margin: '0 auto' }}>
      {/* Hero */}
      <div style={{ textAlign: 'center', paddingTop: 20, marginBottom: 40 }}>
        <h1 style={{ fontSize: '2.4rem', fontWeight: 800, marginBottom: 12 }}>
          Comprendre les emotions<br />sur Twitter
        </h1>
        <p style={{ color: '#71717a', fontSize: '1.05rem', maxWidth: 560, margin: '0 auto 28px' }}>
          Plateforme d'analyse de sentiments alimentee par un RAG from scratch et un LLM specialise.
        </p>
        {!user ? (
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
            <Link to="/login" className="btn-primary">
              Commencer <ArrowRight size={16} />
            </Link>
            <Link to="/about" className="btn-secondary">
              Comment ca marche
            </Link>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
            <Link to="/assistant" className="btn-primary">
              Ouvrir l'assistant <ArrowRight size={16} />
            </Link>
            <Link to="/dashboard" className="btn-secondary">
              Voir le dashboard
            </Link>
          </div>
        )}
      </div>

      {/* Carousel */}
      <Carousel />

      {/* Features grid */}
      <div style={{ marginBottom: 48 }}>
        <h3 style={{ textAlign: 'center', marginBottom: 28, color: '#a1a1aa', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Architecture technique
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          {FEATURES.map((f, i) => (
            <div key={i} className="card" style={{ textAlign: 'center' }}>
              <div style={{ color: '#5271ff', marginBottom: 12, display: 'flex', justifyContent: 'center' }}>{f.icon}</div>
              <h4 style={{ marginBottom: 8, fontSize: '0.9rem' }}>{f.title}</h4>
              <p style={{ color: '#52525b', fontSize: '0.78rem', lineHeight: 1.5 }}>{f.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Pipeline schema */}
      <div className="card" style={{ textAlign: 'center', marginBottom: 48 }}>
        <h3 style={{ marginBottom: 20, color: '#e4e4e7' }}>Pipeline RAG</h3>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, flexWrap: 'wrap' }}>
          {['Question', 'Planner LLM', 'TF-IDF + BM25', 'Re-ranking', 'Groq Generation', 'Reponse'].map((step, i) => (
            <React.Fragment key={i}>
              <div style={{ padding: '8px 14px', background: '#18181b', borderRadius: 6, fontSize: '0.78rem', color: '#e4e4e7', border: '1px solid #27272a' }}>
                {step}
              </div>
              {i < 5 && <ArrowRight size={14} color="#3f3f46" />}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}
