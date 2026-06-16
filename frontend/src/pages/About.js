import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Database, Cpu, MessageSquare, RefreshCw, BarChart3, Zap } from 'lucide-react';

const TEAM = [
  { name: "David", role: "Developpeur Full Stack", desc: "Architecture backend, RAG from scratch, integration LLM" },
  { name: "Louis Seillier", role: "ML / LLM", desc: "Planner TinyGPT from scratch, entrainement et evaluation des modeles" },
  { name: "Rym Fouzari", role: "Data / Analyse", desc: "Pipeline de donnees, analyses statistiques, dashboards analytiques" },
];

const TECH_STACK = [
  { category: "Backend", items: ["FastAPI", "PostgreSQL", "Redis", "Celery", "Kafka"] },
  { category: "IA / ML", items: ["PyTorch (TinyGPT)", "Groq LLaMA 3", "CamemBERT fine-tune"] },
  { category: "RAG", items: ["TF-IDF from scratch", "BM25 Okapi", "RRF", "Query Expansion"] },
  { category: "Frontend", items: ["React 19", "Recharts", "Lucide Icons"] },
  { category: "Infra", items: ["Docker", "MLflow", "MCP Twitter"] },
];

const PIPELINE_STEPS = [
  { icon: <MessageSquare size={20} />, title: "1. Question utilisateur", desc: "L'utilisateur pose une question en langage naturel sur les sentiments Twitter." },
  { icon: <Cpu size={20} />, title: "2. Planner LLM (TinyGPT)", desc: "Un Transformer decoder-only comprend l'intention, extrait les cibles et produit un plan JSON." },
  { icon: <Database size={20} />, title: "3. Retrieval from scratch", desc: "TF-IDF cosine + BM25 + RRF fusionnent les resultats. Query expansion dynamique via co-occurrences." },
  { icon: <RefreshCw size={20} />, title: "4. Re-ranking", desc: "Second passage : scoring contextuel, boost temporel, filtre confiance. Si pas assez → MCP Twitter temps reel." },
  { icon: <Zap size={20} />, title: "5. Generation (Groq)", desc: "Le prompt enrichi est envoye a Groq LLaMA 3 pour une reponse naturelle. Fallback sur TinyGPT si indisponible." },
  { icon: <BarChart3 size={20} />, title: "6. Dashboard + Metriques", desc: "Un dashboard est genere automatiquement. Metriques RAG (NDCG, MRR, faithfulness) calculees." },
];

export default function About() {
  return (
    <div className="animate-in" style={{ maxWidth: 800, margin: '0 auto' }}>
      {/* Hero */}
      <div style={{ textAlign: 'center', paddingTop: 20, marginBottom: 48 }}>
        <h1 style={{ fontSize: '2rem', marginBottom: 12 }}>A propos de SentiFlow</h1>
        <p style={{ color: '#71717a', fontSize: '1rem', maxWidth: 600, margin: '0 auto' }}>
          Plateforme d'analyse de sentiments Twitter construite from scratch. 
          RAG maison, LLM specialise, generation via Groq — le tout sans dependance externe pour le retrieval.
        </p>
      </div>

      {/* Comment ca marche */}
      <section style={{ marginBottom: 56 }}>
        <h2 style={{ marginBottom: 24, fontSize: '1.3rem' }}>Comment ca marche</h2>
        <div style={{ display: 'grid', gap: 12 }}>
          {PIPELINE_STEPS.map((step, i) => (
            <div key={i} className="card" style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
              <div style={{ color: '#5271ff', marginTop: 2 }}>{step.icon}</div>
              <div>
                <h4 style={{ marginBottom: 4, fontSize: '0.92rem' }}>{step.title}</h4>
                <p style={{ color: '#71717a', fontSize: '0.84rem' }}>{step.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Tech Stack */}
      <section style={{ marginBottom: 56 }}>
        <h2 style={{ marginBottom: 24, fontSize: '1.3rem' }}>Stack technique</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
          {TECH_STACK.map((group, i) => (
            <div key={i} className="card">
              <h4 style={{ color: '#5271ff', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
                {group.category}
              </h4>
              <ul style={{ listStyle: 'none', padding: 0 }}>
                {group.items.map((item, j) => (
                  <li key={j} style={{ color: '#a1a1aa', fontSize: '0.82rem', marginBottom: 4 }}>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* From scratch */}
      <section style={{ marginBottom: 56 }}>
        <h2 style={{ marginBottom: 16, fontSize: '1.3rem' }}>Pourquoi "From Scratch" ?</h2>
        <div className="card">
          <p style={{ color: '#a1a1aa', lineHeight: 1.8, fontSize: '0.9rem' }}>
            Le coeur du RAG (retrieval) est entierement code a la main : tokenizer, stemmer francais, 
            TF-IDF vectorizer, BM25, similarite cosinus, index vectoriel, re-ranking. 
            Aucune librairie type LangChain, FAISS, ou sentence-transformers n'est utilisee.
            <br /><br />
            Seules dependances : <strong>NumPy</strong> (calcul matriciel) et <strong>Groq API</strong> (generation finale).
            Le planner (TinyGPT) est un vrai Transformer PyTorch entraine sur nos donnees synthetiques + utilisateurs.
          </p>
        </div>
      </section>

      {/* Equipe */}
      <section style={{ marginBottom: 56 }}>
        <h2 style={{ marginBottom: 24, fontSize: '1.3rem' }}>Equipe</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: 14 }}>
          {TEAM.map((member, i) => (
            <div key={i} className="card" style={{ textAlign: 'center' }}>
              <div style={{ width: 48, height: 48, borderRadius: '50%', background: '#5271ff', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 12px', fontSize: '1.1rem', fontWeight: 700 }}>
                {member.name[0]}
              </div>
              <h4 style={{ marginBottom: 4 }}>{member.name}</h4>
              <p style={{ color: '#5271ff', fontSize: '0.78rem', marginBottom: 8 }}>{member.role}</p>
              <p style={{ color: '#71717a', fontSize: '0.8rem' }}>{member.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <div style={{ textAlign: 'center', marginBottom: 40 }}>
        <Link to="/assistant" className="btn-primary">
          Essayer l'assistant <ArrowRight size={16} />
        </Link>
      </div>
    </div>
  );
}
