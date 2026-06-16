import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { deleteGeneratedDashboard, getGeneratedDashboards } from '../services/api';
import api from '../services/api';
import './GeneratedDashboards.css';

function formatDate(value) {
  if (!value) return '-';
  try {
    return new Date(value).toLocaleString('fr-FR');
  } catch (_err) {
    return String(value);
  }
}

export default function GeneratedDashboards() {
  const [dashboards, setDashboards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadDashboards = async () => {
    setLoading(true);
    setError('');
    try {
      // Chaque utilisateur ne voit QUE ses propres rapports IA
      const response = await getGeneratedDashboards();
      setDashboards(response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || 'Impossible de charger les rapports.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadDashboards(); }, []);

  const handleDelete = async (id) => {
    if (!window.confirm('Supprimer ce dashboard ?')) return;
    try {
      await deleteGeneratedDashboard(id);
      setDashboards((current) => current.filter((d) => d.id !== id));
    } catch (err) {
      setError(err.response?.data?.detail || 'Suppression impossible.');
    }
  };

  const handleDownloadPdf = async (id) => {
    try {
      const res = await api.get(`/dashboards/${id}/pdf`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `rapport_dashboard_${id}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.response?.data?.detail || 'Export PDF impossible.');
    }
  };

  return (
    <div className="generated-dashboard-list-page">
      <div className="generated-dashboard-list-header">
        <div>
          <h1>Mes rapports IA</h1>
          <p>Rapports générés par l'assistant — exportables en PDF.</p>
        </div>
        <Link to="/assistant" className="generated-primary-link">
          Creer via l'assistant
        </Link>
      </div>

      {error && <div className="generated-error-message">{error}</div>}

      {loading ? (
        <p className="generated-info-message">Chargement...</p>
      ) : dashboards.length === 0 ? (
        <div className="generated-empty-state">
          <h2>Aucun dashboard genere</h2>
          <p>
            Utilise l'assistant et demande par exemple :
            <br />
            <strong>compare #france et #minecraft</strong>
          </p>
          <Link to="/assistant" className="generated-primary-link">
            Ouvrir l'assistant
          </Link>
        </div>
      ) : (
        <div className="generated-dashboard-grid">
          {dashboards.map((dashboard) => (
            <article className="generated-dashboard-card" key={dashboard.id}>
              <div>
                <h2>{dashboard.title}</h2>
                <p className="generated-question">{dashboard.question}</p>
              </div>
              <div className="generated-card-meta">
                <span>Cree le {formatDate(dashboard.created_at)}</span>
                {dashboard.user && <span>Par {dashboard.user}</span>}
                <span>{dashboard.target_ids?.length || 0} cible(s)</span>
              </div>
              <div className="dashboard-list-actions">
                <Link to={`/dashboards/generated/${dashboard.id}`} className="generated-secondary-link">
                  Voir le dashboard
                </Link>
                <button type="button" onClick={() => handleDownloadPdf(dashboard.id)}>
                  Export PDF
                </button>
                <button type="button" onClick={() => handleDelete(dashboard.id)}>
                  Supprimer
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
