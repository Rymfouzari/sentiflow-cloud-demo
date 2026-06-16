"""
Générateur de PDF pour les dashboards SentiFlow.
Utilise fpdf2 (pas de dépendance lourde).
"""
import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sentiflow.pdf")

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False


def generate_dashboard_pdf(
    title: str,
    question: str,
    answer: str,
    sources: List[Dict[str, Any]],
    metrics: Optional[Dict[str, Any]] = None,
    sentiment_stats: Optional[Dict[str, Any]] = None,
) -> Optional[bytes]:
    """
    Génère un PDF du dashboard/rapport.
    Retourne les bytes du PDF ou None si fpdf2 n'est pas installé.
    """
    if not FPDF_AVAILABLE:
        logger.warning("[PDF] fpdf2 non installé. pip install fpdf2")
        return None

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Titre
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "SentiFlow - Rapport d'Analyse", ln=True, align="C")
    pdf.ln(5)

    # Date
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Generé le {datetime.utcnow().strftime('%d/%m/%Y a %H:%M')}", ln=True, align="C")
    pdf.ln(10)

    # Question
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Question :", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, _safe_text(question))
    pdf.ln(5)

    # Réponse
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Reponse :", ln=True)
    pdf.set_font("Helvetica", "", 10)
    # Tronquer la réponse si trop longue
    answer_text = _safe_text(answer[:2000])
    pdf.multi_cell(0, 5, answer_text)
    pdf.ln(5)

    # Stats sentiments
    if sentiment_stats:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Distribution des sentiments :", ln=True)
        pdf.set_font("Helvetica", "", 10)
        for sent, count in sentiment_stats.items():
            pdf.cell(0, 6, f"  - {sent} : {count}", ln=True)
        pdf.ln(5)

    # Sources
    if sources:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, f"Sources ({len(sources)} tweets) :", ln=True)
        pdf.set_font("Helvetica", "", 9)
        for i, s in enumerate(sources[:10], 1):
            author = s.get("author", "?")
            sentiment = s.get("sentiment", "?")
            confidence = s.get("confidence", 0)
            text = _safe_text(str(s.get("text", ""))[:150])
            pdf.multi_cell(0, 4, f"{i}. @{author} | {sentiment} ({confidence:.0%}) | \"{text}\"")
            pdf.ln(2)

    # Métriques
    if metrics:
        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Metriques RAG :", ln=True)
        pdf.set_font("Helvetica", "", 9)
        retrieval = metrics.get("retrieval", {})
        timing = metrics.get("timing", {})
        pdf.cell(0, 5, f"  Relevance: {retrieval.get('relevance', 0):.4f}", ln=True)
        pdf.cell(0, 5, f"  Coherence: {retrieval.get('coherence', 0):.4f}", ln=True)
        pdf.cell(0, 5, f"  MRR: {retrieval.get('mrr', 0):.4f}", ln=True)
        pdf.cell(0, 5, f"  Temps total: {timing.get('total', 0):.2f}s", ln=True)

    # Footer
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 5, "SentiFlow - RAG from scratch + MCP + Groq LLM", ln=True, align="C")

    return pdf.output()


def _safe_text(text: str) -> str:
    """Nettoie le texte pour le PDF (enlève les caractères non-latin1)."""
    # fpdf2 avec Helvetica ne supporte que latin-1
    result = ""
    for ch in text:
        try:
            ch.encode("latin-1")
            result += ch
        except (UnicodeEncodeError, UnicodeDecodeError):
            result += "?"
    return result


# Couleurs RGB par sentiment (pour les barres du rapport)
_SENTIMENT_RGB = {
    "joie": (34, 197, 94),
    "amour": (236, 72, 153),
    "colere": (239, 68, 68),
    "tristesse": (59, 130, 246),
    "peur": (168, 85, 247),
    "surprise": (245, 158, 11),
    "neutre": (148, 163, 184),
    "incertain": (148, 163, 184),
}
_SENTIMENT_LABEL = {
    "joie": "Joie", "amour": "Amour", "colere": "Colere", "tristesse": "Tristesse",
    "peur": "Peur", "surprise": "Surprise", "neutre": "Neutre", "incertain": "Incertain",
}


def generate_report_pdf(
    title: str,
    question: str,
    created_at: Optional[str],
    targets: List[Dict[str, Any]],
    tweets: List[Dict[str, Any]],
    synthesis: Optional[str] = None,
) -> Optional[bytes]:
    """
    Génère un PDF "dashboard de tweets" :
    - en-tête + KPIs
    - répartition des sentiments en barres colorées (par cible)
    - tweets représentatifs
    - synthèse LLM en annexe (secondaire)

    Volontairement différent du dashboard interactif global : c'est un rapport
    centré sur les tweets d'UNE requête / d'un ensemble de cibles.
    """
    if not FPDF_AVAILABLE:
        logger.warning("[PDF] fpdf2 non installé. pip install fpdf2")
        return None

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # En-tête
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 11, "SentiFlow - Rapport d'analyse des tweets", ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, _safe_text(f"{title}"), ln=True, align="C")
    pdf.cell(0, 5, f"Genere le {datetime.utcnow().strftime('%d/%m/%Y a %H:%M')}", ln=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    if question:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(70, 70, 70)
        pdf.multi_cell(0, 5, _safe_text(f"Question : {question}"))
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

    # KPIs globaux
    total_all = sum(t.get("total", 0) for t in targets)
    pos_all = sum(t.get("positive", 0) for t in targets)
    neg_all = sum(t.get("negative", 0) for t in targets)
    net = round((pos_all - neg_all) / total_all, 2) if total_all else 0
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Vue d'ensemble", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pct_pos = round(pos_all / total_all * 100) if total_all else 0
    pct_neg = round(neg_all / total_all * 100) if total_all else 0
    pdf.cell(0, 5, f"  Tweets analyses : {total_all}   |   Cibles : {len(targets)}", ln=True)
    pdf.cell(0, 5, f"  Positif : {pct_pos}%   |   Negatif : {pct_neg}%   |   Score net : {'+' if net >= 0 else ''}{net}", ln=True)
    pdf.ln(4)

    # Répartition des sentiments par cible (barres)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Repartition des sentiments par cible", ln=True)
    pdf.ln(1)

    bar_max_w = 110  # largeur max d'une barre en mm
    for t in targets:
        name = _safe_text(str(t.get("name", "?")))
        total = t.get("total", 0) or 0
        dist = t.get("distribution", {}) or {}
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, f"{name}  ({total} tweets)", ln=True)
        pdf.set_font("Helvetica", "", 8)
        for sentiment, ratio in sorted(dist.items(), key=lambda x: x[1], reverse=True):
            if not ratio:
                continue
            rgb = _SENTIMENT_RGB.get(sentiment, (148, 163, 184))
            label = _SENTIMENT_LABEL.get(sentiment, sentiment)
            y = pdf.get_y()
            pdf.set_x(15)
            pdf.cell(28, 5, label, ln=0)
            # barre
            pdf.set_fill_color(*rgb)
            w = max(1.0, bar_max_w * float(ratio))
            pdf.rect(45, y + 0.8, w, 3.5, style="F")
            pdf.set_xy(45 + w + 2, y)
            pdf.cell(0, 5, f"{round(float(ratio) * 100)}%", ln=True)
        pdf.ln(2)

    # Tweets représentatifs
    if tweets:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, f"Tweets representatifs ({min(len(tweets), 12)})", ln=True)
        pdf.set_font("Helvetica", "", 8)
        for i, s in enumerate(tweets[:12], 1):
            author = _safe_text(str(s.get("author", "?")))
            sentiment = s.get("sentiment", "?")
            conf = s.get("confidence", 0) or 0
            text = _safe_text(str(s.get("text", ""))[:160])
            rgb = _SENTIMENT_RGB.get(sentiment, (100, 100, 100))
            pdf.set_text_color(*rgb)
            pdf.cell(0, 4.5, f"{i}. @{author} - {sentiment} ({conf:.0%})", ln=True)
            pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(0, 4, f"   {text}")
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)

    # Synthèse LLM (annexe)
    if synthesis:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Synthese (assistant IA)", ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(60, 60, 60)
        pdf.multi_cell(0, 5, _safe_text(synthesis[:1800]))
        pdf.set_text_color(0, 0, 0)

    # Footer
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, "SentiFlow - Rapport genere automatiquement", ln=True, align="C")

    return pdf.output()
