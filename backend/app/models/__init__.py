from backend.app.models.user import User
from backend.app.models.target import Target
from backend.app.models.tweet import Tweet
from backend.app.models.alert import Alert
from backend.app.models.account import Account
from backend.app.models.sentiment_aggregate import SentimentAggregate
from backend.app.models.dashboard import Dashboard, DashboardExport
from backend.app.models.feedback import Feedback

try:
    from backend.app.models.generated_dashboard import GeneratedDashboard
except ImportError:
    GeneratedDashboard = None

try:
    from backend.app.models.llm_feedback import LLMFeedback
except ImportError:
    LLMFeedback = None

try:
    from backend.app.models.embedding import TweetEmbedding
except ImportError:
    TweetEmbedding = None

try:
    from backend.app.models.prediction_log import PredictionLog
except ImportError:
    PredictionLog = None

try:
    from backend.app.models.drift_log import DriftLog
except ImportError:
    DriftLog = None

try:
    from backend.app.models.question_log import QuestionLog
except ImportError:
    QuestionLog = None

try:
    from backend.app.models.ticket import Ticket
except ImportError:
    Ticket = None

__all__ = [
    "User", "Target", "Tweet", "Alert",
    "Account", "SentimentAggregate",
    "Dashboard", "DashboardExport", "Feedback",
    "GeneratedDashboard", "LLMFeedback",
    "TweetEmbedding", "PredictionLog", "DriftLog",
    "QuestionLog", "Ticket",
]
