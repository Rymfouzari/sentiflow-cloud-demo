import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import sys
sys.path.append("..")
from components.api import get_targets, get_analysis

st.title("📊 Dashboard")

if not st.session_state.get("token"):
    st.warning("Veuillez vous connecter")
    st.stop()

# Récupérer les cibles
targets = get_targets()

if not targets:
    st.info("Aucune cible configurée. Ajoutez des hashtags ou comptes à suivre.")
    st.page_link("pages/3_Cibles.py", label="Ajouter une cible", icon="➕")
    st.stop()

# Sélection de la cible
col1, col2 = st.columns([2, 1])
with col1:
    target_names = {t["id"]: t["name"] for t in targets}
    selected_id = st.selectbox(
        "Cible",
        options=list(target_names.keys()),
        format_func=lambda x: target_names[x]
    )
with col2:
    days = st.selectbox("Période", [7, 14, 30], format_func=lambda x: f"{x} jours")

# Récupérer l'analyse
analysis = get_analysis(selected_id, days)

if not analysis or analysis["total_tweets"] == 0:
    st.warning("Pas encore de données pour cette cible")
    st.stop()

# Métriques
st.subheader(f"Analyse de {analysis['target_name']}")
col1, col2, col3 = st.columns(3)
col1.metric("Tweets analysés", analysis["total_tweets"])
col2.metric("Période", analysis["period"])
col3.metric("Confiance moyenne", f"{analysis['average_confidence']:.1%}")

# Graphiques
col1, col2 = st.columns(2)

with col1:
    # Pie chart
    dist = analysis["sentiment_distribution"]
    fig = px.pie(
        values=list(dist.values()),
        names=list(dist.keys()),
        title="Répartition des sentiments",
        color_discrete_sequence=px.colors.qualitative.Set2
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    # Bar chart
    fig = go.Figure(data=[
        go.Bar(
            x=list(dist.keys()),
            y=[v * 100 for v in dist.values()],
            marker_color=px.colors.qualitative.Set2
        )
    ])
    fig.update_layout(
        title="Sentiments (%)",
        yaxis_title="Pourcentage",
        xaxis_title="Sentiment"
    )
    st.plotly_chart(fig, use_container_width=True)
