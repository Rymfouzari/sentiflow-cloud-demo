import streamlit as st
import sys
sys.path.append("..")
from components.api import get_targets, get_alerts, create_alert

st.title("🔔 Alertes")

if not st.session_state.get("token"):
    st.warning("Veuillez vous connecter")
    st.stop()

SENTIMENTS = ["joie", "colere", "tristesse", "peur", "surprise", "neutre"]

# Formulaire d'ajout
st.subheader("Créer une alerte")
targets = get_targets()

if not targets:
    st.info("Ajoutez d'abord des cibles à suivre")
    st.stop()

with st.form("add_alert"):
    target_names = {t["id"]: t["name"] for t in targets}
    target_id = st.selectbox(
        "Cible",
        options=list(target_names.keys()),
        format_func=lambda x: target_names[x]
    )
    
    name = st.text_input("Nom de l'alerte", placeholder="Alerte colère élevée")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        sentiment = st.selectbox("Sentiment", SENTIMENTS)
    with col2:
        threshold = st.slider("Seuil (%)", 10, 90, 50) / 100
    with col3:
        is_above = st.radio("Condition", ["Supérieur à", "Inférieur à"]) == "Supérieur à"
    
    submitted = st.form_submit_button("Créer l'alerte")
    if submitted and name:
        result = create_alert(target_id, name, sentiment, threshold, is_above)
        if result:
            st.success("Alerte créée !")
            st.rerun()
        else:
            st.error("Erreur lors de la création")

# Liste des alertes
st.subheader("Alertes actives")
alerts = get_alerts()

if not alerts:
    st.info("Aucune alerte configurée")
else:
    for alert in alerts:
        condition = ">" if alert["is_above"] else "<"
        status = "🟢" if alert["is_active"] else "🔴"
        st.write(f"{status} **{alert['name']}** - {alert['sentiment']} {condition} {alert['threshold']:.0%}")
