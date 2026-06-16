import React from 'react';
import {
  BarChart,
  Bar,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import './GeneratedDashboardRenderer.css';

const SENTIMENTS = ['joie', 'amour', 'colere', 'tristesse', 'peur', 'surprise', 'neutre'];
const SENTIMENT_LABELS = {
  joie: 'Joie',
  amour: 'Amour',
  colere: 'Colère',
  tristesse: 'Tristesse',
  peur: 'Peur',
  surprise: 'Surprise',
  neutre: 'Neutre',
};
const SENTIMENT_COLORS = {
  joie: '#22c55e',
  amour: '#ec4899',
  colere: '#ef4444',
  tristesse: '#3b82f6',
  peur: '#a855f7',
  surprise: '#f59e0b',
  neutre: '#94a3b8',
};
const SERIES_COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#a855f7', '#ec4899', '#14b8a6'];

function percent(value) {
  const numeric = Number(value || 0);
  if (numeric <= 1) return `${Math.round(numeric * 100)}%`;
  return `${Math.round(numeric)}%`;
}

function score(value) {
  const numeric = Number(value || 0);
  return numeric > 0 ? `+${numeric.toFixed(2)}` : numeric.toFixed(2);
}

function formatDate(value) {
  if (!value) return '';
  try {
    return new Date(value).toLocaleString('fr-FR');
  } catch (_err) {
    return String(value);
  }
}

function getWidget(config, type) {
  return config?.widgets?.find((widget) => widget.type === type);
}

function countsToChartData(item) {
  const counts = item?.counts || {};
  const distribution = item?.distribution || {};
  return SENTIMENTS.map((sentiment) => ({
    sentiment,
    name: SENTIMENT_LABELS[sentiment] || sentiment,
    value: Number(counts[sentiment] ?? 0),
    percent: Number(distribution[sentiment] ?? 0),
  })).filter((row) => row.value > 0 || row.percent > 0);
}

function buildTargetMetrics(distributionWidget, insightWidget) {
  const distributionTargets = distributionWidget?.data || [];
  const insights = insightWidget?.data || [];
  const insightByTarget = Object.fromEntries(
    insights.map((item) => [String(item.target_id || item.target_name), item])
  );

  return distributionTargets.map((target) => {
    const counts = target.counts || {};
    const distribution = target.distribution || {};
    const total = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);
    const dominant = SENTIMENTS.reduce(
      (best, sentiment) => Number(distribution[sentiment] || 0) > Number(distribution[best] || 0) ? sentiment : best,
      SENTIMENTS[0]
    );
    const insight = insightByTarget[String(target.target_id)] || insightByTarget[String(target.target_name)] || {};

    return {
      targetId: target.target_id,
      targetName: target.target_name,
      total,
      dominant,
      dominantPercent: Number(distribution[dominant] || 0),
      netScore: insight.net_sentiment_score,
    };
  });
}

function buildComparisonData(comparisonWidget, distributionWidget) {
  const dataSource = comparisonWidget?.data || distributionWidget?.data || [];

  return dataSource.map((target) => {
    const distribution = target.sentiment_distribution || target.distribution || {};
    const row = {
      targetName: target.target_name,
      total_tweets: target.total_tweets || Object.values(target.counts || {}).reduce((sum, value) => sum + Number(value || 0), 0),
      dominant_sentiment: target.dominant_sentiment,
      net_sentiment_score: target.net_sentiment_score,
    };

    SENTIMENTS.forEach((sentiment) => {
      row[sentiment] = Math.round(Number(distribution[sentiment] || 0) * 100);
    });

    return row;
  });
}

function buildTimelineData(timelineWidget) {
  const raw = timelineWidget?.data || {};
  const rowsByDate = {};
  const targetNames = Object.keys(raw || {});

  targetNames.forEach((targetName) => {
    (raw[targetName] || []).forEach((point) => {
      const date = point.date;
      if (!rowsByDate[date]) rowsByDate[date] = { date };
      rowsByDate[date][targetName] = Number(point.net_sentiment_score ?? point.total ?? 0);
    });
  });

  return {
    targetNames,
    rows: Object.values(rowsByDate).sort((a, b) => String(a.date).localeCompare(String(b.date))),
  };
}

function buildKeywordRows(keywordWidget) {
  const rows = [];
  (keywordWidget?.data || []).forEach((target) => {
    (target.keywords || []).forEach((keyword) => {
      rows.push({
        targetName: target.target_name,
        term: keyword.term,
        count: Number(keyword.count || 0),
        label: `${target.target_name} — ${keyword.term}`,
      });
    });
  });
  return rows.slice(0, 18);
}

function DashboardMetrics({ metrics }) {
  const totalTweets = metrics.reduce((sum, item) => sum + item.total, 0);
  const targetCount = metrics.length;
  const mostActive = metrics.reduce((best, item) => item.total > (best?.total || 0) ? item : best, null);
  const avgNetScore = metrics.length
    ? metrics.reduce((sum, item) => sum + Number(item.netScore || 0), 0) / metrics.length
    : 0;

  return (
    <div className="generated-dashboard-metrics">
      <div className="generated-metric-card">
        <span className="generated-metric-value">{targetCount}</span>
        <span className="generated-metric-label">Cibles</span>
      </div>
      <div className="generated-metric-card">
        <span className="generated-metric-value">{totalTweets}</span>
        <span className="generated-metric-label">Tweets analysés</span>
      </div>
      <div className="generated-metric-card">
        <span className="generated-metric-value">{score(avgNetScore)}</span>
        <span className="generated-metric-label">Score émotionnel moyen</span>
      </div>
      <div className="generated-metric-card">
        <span className="generated-metric-value">{mostActive?.targetName || '-'}</span>
        <span className="generated-metric-label">Cible la plus active</span>
      </div>
    </div>
  );
}

function InsightSummaryWidget({ widget }) {
  if (!widget?.data?.length) return null;

  return (
    <section className="generated-widget-card">
      <div className="generated-widget-header">
        <h2>{widget.title || 'Insights automatiques'}</h2>
        <p>Lecture synthétique produite à partir des statistiques calculées sur les tweets analysés.</p>
      </div>
      <div className="generated-insight-grid">
        {widget.data.map((item) => (
          <article className="generated-insight-card" key={item.target_id || item.target_name}>
            <h3>{item.target_name}</h3>
            <div className="generated-insight-score">{score(item.net_sentiment_score)}</div>
            <p>{item.net_sentiment_label || 'Lecture non disponible'}</p>
            <div className="generated-insight-stats">
              <span>Positif : <strong>{percent(item.positive_ratio)}</strong></span>
              <span>Négatif : <strong>{percent(item.negative_ratio)}</strong></span>
              <span>Confiance : <strong>{percent(item.average_confidence)}</strong></span>
            </div>
            {item.trend && (
              <p className="generated-insight-note">
                Tendance : {item.trend.label || item.trend.direction || 'stable'}
                {typeof item.trend.delta_score === 'number' ? ` (${score(item.trend.delta_score)})` : ''}
              </p>
            )}
            {item.quality_notes?.length > 0 && (
              <ul className="generated-quality-list">
                {item.quality_notes.map((note, index) => <li key={index}>{note}</li>)}
              </ul>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function SentimentDistributionWidget({ widget }) {
  if (!widget?.data?.length) return null;

  return (
    <section className="generated-widget-card">
      <div className="generated-widget-header">
        <h2>{widget.title || 'Répartition des sentiments'}</h2>
        <p>Distribution par cible à partir des tweets analysés.</p>
      </div>

      <div className="generated-pie-grid">
        {widget.data.map((target) => {
          const chartData = countsToChartData(target);
          return (
            <div className="generated-pie-card" key={target.target_id || target.target_name}>
              <h3>{target.target_name}</h3>
              {chartData.length === 0 ? (
                <p className="generated-empty">Pas de données.</p>
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={230}>
                    <PieChart>
                      <Pie data={chartData} dataKey="value" nameKey="name" innerRadius={45} outerRadius={78} paddingAngle={2}>
                        {chartData.map((entry) => (
                          <Cell key={entry.sentiment} fill={SENTIMENT_COLORS[entry.sentiment]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value, name, item) => [`${value} tweets (${percent(item.payload.percent)})`, name]} />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>

                  <div className="generated-sentiment-list">
                    {chartData.map((row) => (
                      <div className="generated-sentiment-row" key={row.sentiment}>
                        <span className="generated-dot" style={{ background: SENTIMENT_COLORS[row.sentiment] }} />
                        <span>{row.name}</span>
                        <strong>{row.value} ({percent(row.percent)})</strong>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function TargetComparisonWidget({ comparisonWidget, distributionWidget }) {
  const chartData = buildComparisonData(comparisonWidget, distributionWidget);
  if (!chartData.length || chartData.length < 2) return null;

  return (
    <section className="generated-widget-card">
      <div className="generated-widget-header">
        <h2>{comparisonWidget?.title || 'Comparaison des cibles'}</h2>
        <p>Comparaison en pourcentage par sentiment.</p>
      </div>

      <ResponsiveContainer width="100%" height={360}>
        <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#273244" />
          <XAxis dataKey="targetName" stroke="#94a3b8" />
          <YAxis stroke="#94a3b8" unit="%" />
          <Tooltip formatter={(value, name) => [`${value}%`, SENTIMENT_LABELS[name] || name]} />
          <Legend formatter={(value) => SENTIMENT_LABELS[value] || value} />
          {SENTIMENTS.map((sentiment) => (
            <Bar key={sentiment} dataKey={sentiment} stackId="sentiments" fill={SENTIMENT_COLORS[sentiment]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

function SentimentTimelineWidget({ widget }) {
  const timeline = buildTimelineData(widget);
  if (!timeline.rows.length) return null;

  return (
    <section className="generated-widget-card">
      <div className="generated-widget-header">
        <h2>{widget?.title || 'Évolution temporelle'}</h2>
        <p>Score émotionnel par jour et par cible. Un score positif indique une tonalité plus favorable.</p>
      </div>

      <ResponsiveContainer width="100%" height={340}>
        <LineChart data={timeline.rows} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#273244" />
          <XAxis dataKey="date" stroke="#94a3b8" />
          <YAxis stroke="#94a3b8" domain={[-1, 1]} />
          <Tooltip />
          <Legend />
          {timeline.targetNames.map((targetName, index) => (
            <Line
              key={targetName}
              type="monotone"
              dataKey={targetName}
              stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
              strokeWidth={3}
              dot={{ r: 4 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </section>
  );
}

function KeywordTopicsWidget({ widget }) {
  const rows = buildKeywordRows(widget);
  if (!rows.length) return null;

  return (
    <section className="generated-widget-card">
      <div className="generated-widget-header">
        <h2>{widget.title || 'Mots et sujets récurrents'}</h2>
        <p>Mots les plus fréquents dans les tweets collectés, après nettoyage simple.</p>
      </div>

      <ResponsiveContainer width="100%" height={Math.max(280, rows.length * 26)}>
        <BarChart data={rows} layout="vertical" margin={{ top: 10, right: 20, left: 110, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#273244" />
          <XAxis type="number" stroke="#94a3b8" allowDecimals={false} />
          <YAxis type="category" dataKey="label" stroke="#94a3b8" width={120} />
          <Tooltip formatter={(value) => [`${value} occurrences`, 'Fréquence']} />
          <Bar dataKey="count" fill="#ef4444" radius={[0, 8, 8, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

export default function GeneratedDashboardRenderer({ dashboard, config }) {
  const dashboardConfig = config || dashboard?.config_json || dashboard?.dashboard_config;

  if (!dashboardConfig) {
    return <p className="generated-empty">Aucune configuration de dashboard disponible.</p>;
  }

  const distributionWidget = getWidget(dashboardConfig, 'sentiment_distribution');
  const insightWidget = getWidget(dashboardConfig, 'insight_summary');
  const comparisonWidget = getWidget(dashboardConfig, 'target_comparison');
  const timelineWidget = getWidget(dashboardConfig, 'sentiment_timeline');
  const keywordWidget = getWidget(dashboardConfig, 'keyword_topics');
  const metrics = buildTargetMetrics(distributionWidget, insightWidget);

  return (
    <div className="generated-dashboard-renderer">
      <header className="generated-dashboard-hero">
        <div>
          <p className="generated-dashboard-kicker">Dashboard généré par le LLM</p>
          <h1>{dashboard?.title || dashboardConfig.title || 'Dashboard généré'}</h1>
          <p className="generated-dashboard-question">
            Question : {dashboard?.question || dashboardConfig.source_question || 'Non renseignée'}
          </p>
        </div>
        <div className="generated-dashboard-date">
          <span>Créé le</span>
          <strong>{formatDate(dashboard?.created_at || dashboardConfig.generated_at || dashboardConfig.saved_at)}</strong>
        </div>
      </header>

      {metrics.length > 0 && <DashboardMetrics metrics={metrics} />}

      <InsightSummaryWidget widget={insightWidget} />
      <SentimentDistributionWidget widget={distributionWidget} />
      <TargetComparisonWidget comparisonWidget={comparisonWidget} distributionWidget={distributionWidget} />
      <SentimentTimelineWidget widget={timelineWidget} />
      <KeywordTopicsWidget widget={keywordWidget} />

      {dashboard?.answer && (
        <section className="generated-widget-card generated-answer-card">
          <div className="generated-widget-header">
            <h2>Synthèse LLM</h2>
          </div>
          <p>{dashboard.answer}</p>
        </section>
      )}
    </div>
  );
}
