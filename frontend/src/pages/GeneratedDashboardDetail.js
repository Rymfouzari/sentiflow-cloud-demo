import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import GeneratedDashboardRenderer from '../components/GeneratedDashboardRenderer';
import api, { getGeneratedDashboard } from '../services/api';
import './GeneratedDashboards.css';

export default function GeneratedDashboardDetail() {
  const { id } = useParams();
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');

    getGeneratedDashboard(id)
      .then((response) => setDashboard(response.data))
      .catch((err) => setError(err.response?.data?.detail || 'Dashboard introuvable.'))
      .finally(() => setLoading(false));
  }, [id]);

  const handleExportPdf = async () => {
    try {
      const res = await api.get(`/dashboards/${id}/pdf`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `rapport_dashboard_${id}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      window.print(); // fallback
    }
  };

  const jsonDownloadUrl = useMemo(() => {
    if (!dashboard) return null;
    const blob = new Blob([JSON.stringify(dashboard, null, 2)], { type: 'application/json' });
    return URL.createObjectURL(blob);
  }, [dashboard]);

  return (
    <div className="generated-dashboard-detail-page">
      <div className="generated-dashboard-actions">
        <Link to="/dashboards/generated" className="generated-secondary-link">
          ← Retour
        </Link>
        {dashboard && (
          <>
            <button type="button" onClick={handleExportPdf}>
              Exporter en PDF
            </button>
            {jsonDownloadUrl && (
              <a
                className="generated-secondary-link"
                href={jsonDownloadUrl}
                download={`sentiflow-dashboard-${dashboard.id}.json`}
              >
                Télécharger JSON
              </a>
            )}
          </>
        )}
      </div>

      {loading ? (
        <p className="generated-info-message">Chargement du dashboard...</p>
      ) : error ? (
        <div className="generated-error-message">{error}</div>
      ) : (
        <GeneratedDashboardRenderer dashboard={dashboard} />
      )}
    </div>
  );
}
