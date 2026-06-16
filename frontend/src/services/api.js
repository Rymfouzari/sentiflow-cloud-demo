import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || '';

const api = axios.create({
  baseURL: API_URL,
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error.response?.status === 401 &&
      !error.config?.url?.startsWith('/auth/')
    ) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }

    return Promise.reject(error);
  }
);

function demoResponse(data) {
  return Promise.resolve({ data });
}

function normalizeTarget(target) {
  return {
    ...target,
    id: target.targetId,
    target_id: target.targetId,
    target_type: target.targetType,
  };
}

function normalizeTargetsResponse(response) {
  const items = response.data?.items || [];

  return {
    ...response,
    data: items.map(normalizeTarget),
  };
}

function normalizeCreateTargetResponse(response) {
  return {
    ...response,
    data: normalizeTarget(response.data),
  };
}

function normalizeCollectTweetsResponse(response) {
  const created = response.data?.created || 0;

  return {
    ...response,
    data: {
      ...response.data,
      saved: created,
      tweets_saved: created,
    },
  };
}

function normalizeTweetsResponse(response) {
  const items = response.data?.items || [];

  return {
    ...response,
    data: items,
  };
}

function normalizeAnalysisResponse(response) {
  const dashboard = response.data || {};
  const distribution = dashboard.sentimentDistribution || {};
  const percentages = dashboard.sentimentPercentages || {};

  return {
    ...response,
    data: {
      ...dashboard,
      total_tweets: dashboard.totalTweets || 0,
      analyzed_tweets: dashboard.analyzedTweets || 0,
      average_confidence: dashboard.averageConfidence || 0,
      sentiment_distribution: {
        positive: (percentages.positive || 0) / 100,
        neutral: (percentages.neutral || 0) / 100,
        negative: (percentages.negative || 0) / 100,
      },
      counts: {
        positive: distribution.positive || 0,
        neutral: distribution.neutral || 0,
        negative: distribution.negative || 0,
        unknown: distribution.unknown || 0,
      },
    },
  };
}

function buildAnalyticsDashboardFromOverview(overview) {
  const target = overview.target || {};
  const dashboard = overview.dashboard || {};
  const tweets = overview.tweets?.items || [];

  const distribution = dashboard.sentimentDistribution || {
    positive: 0,
    neutral: 0,
    negative: 0,
    unknown: 0,
  };

  const total = dashboard.totalTweets || tweets.length || 0;
  const positive = distribution.positive || 0;
  const neutral = distribution.neutral || 0;
  const negative = distribution.negative || 0;

  const positiveRate = total ? positive / total : 0;
  const neutralRate = total ? neutral / total : 0;
  const negativeRate = total ? negative / total : 0;
  const netScore = positiveRate - negativeRate;

  return {
    has_data: total > 0,
    message:
      total > 0
        ? ''
        : 'Aucune donnée disponible. Ajoute une cible puis collecte/analyse des tweets.',
    plan_advanced: false,

    kpis: {
      total_mentions: total,
      total_tweets: total,
      analyzed_tweets: dashboard.analyzedTweets || 0,

      positive_share: positiveRate,
      neutral_share: neutralRate,
      negative_share: negativeRate,

      positive_percent: Math.round(positiveRate * 100),
      neutral_percent: Math.round(neutralRate * 100),
      negative_percent: Math.round(negativeRate * 100),

      positive_pct: Math.round(positiveRate * 100),
      neutral_pct: Math.round(neutralRate * 100),
      negative_pct: Math.round(negativeRate * 100),

      positive_rate: positiveRate,
      neutral_rate: neutralRate,
      negative_rate: negativeRate,

      positive,
      neutral,
      negative,

      net_score: Math.round(netScore * 100),
      average_confidence: dashboard.averageConfidence || 0,
      avg_confidence: dashboard.averageConfidence || 0,
      confidence_percent: Math.round((dashboard.averageConfidence || 0) * 100),
    },

    targets_breakdown: [
      {
        id: target.targetId,
        targetId: target.targetId,
        name: target.name || 'Target',
        value: total,
        total,
        positive,
        neutral,
        negative,
      },
    ],

    insights: [
      {
        tone: 'neutral',
        icon: '📊',
        text: `${target.name || 'Cette cible'} a ${total} tweet(s) analysé(s).`,
      },
      {
        tone: positive >= negative ? 'positive' : 'negative',
        icon: positive >= negative ? '✅' : '⚠️',
        text: `Répartition : ${positive} positif(s), ${neutral} neutre(s), ${negative} négatif(s).`,
      },
      {
        tone: 'neutral',
        icon: '🎯',
        text: `Confiance moyenne : ${Math.round(
          (dashboard.averageConfidence || 0) * 100
        )} %.`,
      },
    ],

    sentiment_timeline: [
      {
        date: 'Démo',
        positive,
        neutral,
        negative,
      },
    ],

    timeline: [
      {
        date: 'Démo',
        positive,
        neutral,
        negative,
      },
    ],

    share_of_voice: [
      {
        name: target.name || 'Target',
        value: total,
      },
    ],

    keywords: {
      positive: [
        { word: 'optimistes', count: positive },
        { word: 'fonctionnalité', count: positive },
      ].filter((w) => w.count > 0),
      negative: [
        { word: 'critiquent', count: negative },
        { word: 'prix élevés', count: negative },
      ].filter((w) => w.count > 0),
    },

    pca: {
      available: false,
      message: 'Carte des sujets désactivée dans la V1 Cloud.',
      points: [],
      clusters: [],
    },

    correlation: {
      available: false,
      message: 'Similarité avancée désactivée dans la V1 Cloud.',
      labels: [],
      matrix: [],
    },

    raw_overview: overview,
  };
}

// Auth mock pour la V1 Cloud
export const login = async (email, password) => {
  const user = {
    id: 'demo',
    email,
    username: email?.split('@')[0] || 'demo',
    is_admin: false,
    plan: 'demo',
  };

  return {
    data: {
      access_token: 'demo-token',
      user,
    },
  };
};

export const register = async (email, username, password) => {
  const user = {
    id: 'demo',
    email,
    username: username || email?.split('@')[0] || 'demo',
    is_admin: false,
    plan: 'demo',
  };

  return {
    data: {
      access_token: 'demo-token',
      user,
    },
  };
};

export const getMe = async () => {
  return {
    data: {
      id: 'demo',
      email: 'demo@sentiflow.local',
      username: 'demo',
      is_admin: false,
      plan: 'demo',
    },
  };
};

// Targets
export const getTargets = () =>
  api.get('/targets').then(normalizeTargetsResponse);

export const createTarget = (nameOrPayload, targetType) => {
  const rawPayload =
    typeof nameOrPayload === 'object'
      ? nameOrPayload
      : { name: nameOrPayload, target_type: targetType };

  const payload = {
    name: rawPayload.name,
    query: rawPayload.query || rawPayload.name,
    targetType: rawPayload.targetType || rawPayload.target_type || 'keyword',
  };

  return api.post('/targets', payload).then(normalizeCreateTargetResponse);
};

export const deleteTarget = async (id) => {
  console.warn('deleteTarget non implémenté côté Lambda pour l’instant:', id);
  return { data: { ok: true, id } };
};

// Twitter mock
export const verifyTarget = async (id) => {
  return { data: { ok: true, id, verified: true } };
};

export const collectTweets = (id) =>
  api
    .post('/tweets/mock', { targetId: id }, { timeout: 120000 })
    .then(normalizeCollectTweetsResponse);

// Analysis mock
export const analyzeTweets = (id) =>
  api.post('/sentiment/mock', { targetId: id }, { timeout: 180000 });

export const getAnalysis = (id, days = 7) =>
  api
    .get('/dashboard', { params: { targetId: id, days } })
    .then(normalizeAnalysisResponse);

// Tweets
export const getTweets = (id, limit = 50) =>
  api
    .get('/tweets', { params: { targetId: id, limit } })
    .then(normalizeTweetsResponse);

// Overview
export const getOverview = (id) =>
  api.get('/overview', { params: { targetId: id } });

// Dashboard app-v2
export const getAnalyticsDashboard = async (days = 30, targetIds = null) => {
  const targetsRes = await api.get('/targets');
  const targets = targetsRes.data?.items || [];

  if (!targets.length) {
    return {
      data: {
        has_data: false,
        message:
          'Aucune cible disponible. Va dans Cibles, ajoute Tesla, puis collecte et analyse les tweets.',
      },
    };
  }

  const selectedTargetId = targetIds?.[0] || targets[0].targetId;

  const overviewRes = await api.get('/overview', {
    params: { targetId: selectedTargetId, days },
  });

  return {
    data: buildAnalyticsDashboardFromOverview(overviewRes.data),
  };
};

// Alerts non branchées dans la V1 Cloud
export const getAlerts = async () => demoResponse([]);
export const createAlert = async (data) => demoResponse(data);

// Tasks non branchées dans la V1 Cloud
export const triggerCollectAll = async () => demoResponse({ ok: true });
export const triggerAnalyzeAll = async () => demoResponse({ ok: true });

// LLM / Assistant version démo
export const askLlm = async (data) =>
  demoResponse({
    answer: 'LLM non branché dans la V1 Cloud.',
    input: data,
  });

export const askLlmAgent = async (data) =>
  demoResponse({
    answer: 'Agent LLM non branché dans la V1 Cloud.',
    input: data,
  });

export const getLlmModelInfo = async () =>
  demoResponse({
    mode: 'demo',
    model: 'not-connected-yet',
  });

export const assistantChat = async (data) => {
  let overview = null;

  try {
    const targetsRes = await api.get('/targets');
    const targets = targetsRes.data?.items || [];

    if (targets.length) {
      const targetId = targets[0].targetId;
      const overviewRes = await api.get('/overview', {
        params: { targetId },
      });
      overview = overviewRes.data;
    }
  } catch (err) {
    overview = null;
  }

  if (!overview) {
    return demoResponse({
      answer:
        "Je n'ai pas encore assez de données. Ajoute une cible, collecte des tweets, puis lance l'analyse.",
      total_retrieved: 0,
      mode: 'database',
      sources: [],
    });
  }

  const dashboard = overview.dashboard || {};
  const target = overview.target || {};
  const distribution = dashboard.sentimentDistribution || {};

  return demoResponse({
    answer:
      `Pour ${target.name || 'cette cible'}, j’ai trouvé ` +
      `${dashboard.totalTweets || 0} tweet(s) analysé(s). ` +
      `Répartition : ${distribution.positive || 0} positif(s), ` +
      `${distribution.neutral || 0} neutre(s), ` +
      `${distribution.negative || 0} négatif(s). ` +
      `La confiance moyenne est de ${Math.round(
        (dashboard.averageConfidence || 0) * 100
      )} %.`,
    total_retrieved: dashboard.totalTweets || 0,
    mode: 'database',
    generator: 'lambda_demo',
    sources: overview.tweets?.items || [],
    metrics: {
      timing: {
        total: 0.1,
      },
    },
  });
};

// Feedback
export const sendSentimentFeedback = async (data) => demoResponse(data);
export const sendLlmFeedback = async (data) => demoResponse(data);

// Generated dashboards
export const getGeneratedDashboards = async () => demoResponse([]);
export const getGeneratedDashboard = async (id) => demoResponse(null);
export const createGeneratedDashboard = async (data) => demoResponse(data);
export const deleteGeneratedDashboard = async (id) =>
  demoResponse({ ok: true, id });

// RAG stubs
export const ragChat = async (data) =>
  demoResponse({
    answer: 'RAG non branché dans la V1 Cloud.',
    input: data,
  });

export const ragIndex = async (data) => demoResponse({ ok: true });
export const ragInfo = async () => demoResponse({ mode: 'demo' });
export const ragMcpTools = async () => demoResponse([]);
export const ragMcpCall = async (toolName, args) =>
  demoResponse({ toolName, args });
export const ragEvaluate = async (data) => demoResponse({ ok: true });

// Abonnement / plan
export const getMyPlan = async () =>
  demoResponse({
    name: 'demo',
    plan: 'demo',
    advanced_dashboard: false,
  });

// Tickets support
export const createTicket = async (data) => demoResponse(data);
export const getMyTickets = async () => demoResponse([]);
export const adminAllTickets = async (status) => demoResponse([]);
export const adminCountOpenTickets = async () => demoResponse({ count: 0 });
export const adminRespondTicket = async (id, data) =>
  demoResponse({ id, ...data });

// Admin
export const adminQuestionLogs = async (limit = 100) => demoResponse([]);
export const adminListUsers = async () => demoResponse([]);
export const adminSetUserPlan = async (userId, plan) =>
  demoResponse({ userId, plan });

export default api;
