import streamlit as st
import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from components.api import (
    get_targets, create_target, delete_target,
    verify_target, collect_tweets, analyze_tweets, get_tweets, get_analysis
)

st.title("🎯 Gérer les cibles")

if not st.session_state.get("token"):
    st.warning("Veuillez vous connecter")
    st.stop()

# --- Statut API ---
try:
    from components.api import get_me
    me = get_me()
    if me:
        st.sidebar.success("🟢 API connectée")
    else:
        st.sidebar.error("🔴 API non connectée")
except:
    st.sidebar.error("🔴 API non connectée")

# --- Ajouter une cible ---
st.subheader("➕ Ajouter une cible")
with st.form("add_target"):
    col1, col2 = st.columns([3, 1])
    with col1:
        name = st.text_input("Hashtag ou compte", placeholder="#MachineLearning ou @elonmusk")
    with col2:
        target_type = st.selectbox("Type", ["hashtag", "account"])

    if st.form_submit_button("Ajouter") and name:
        result = create_target(name, target_type)
        if result:
            st.success(f"✅ Cible '{name}' ajoutée!")
            st.rerun()
        else:
            st.error("Erreur lors de l'ajout")

st.divider()

# --- Liste des cibles ---
st.subheader("📋 Cibles actuelles")
targets = get_targets()

if not targets:
    st.info("Aucune cible configurée. Ajoutez un hashtag ou un compte ci-dessus.")
    st.stop()

EMOJIS = {"joie": "😊", "tristesse": "😢", "colere": "😠", "peur": "😨", "surprise": "😲", "amour": "❤️"}

for target in targets:
    icon = "#️⃣" if target["target_type"] == "hashtag" else "👤"

    with st.container(border=True):
        # --- En-tête cible ---
        header_col, del_col = st.columns([6, 1])
        with header_col:
            st.markdown(f"### {icon} {target['name']}")
        with del_col:
            if st.button("🗑️", key=f"x_{target['id']}", help="Supprimer"):
                delete_target(target["id"])
                st.rerun()

        # --- Boutons d'action ---
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if st.button("✅ Vérifier", key=f"v_{target['id']}"):
                with st.spinner("Vérification..."):
                    result = verify_target(target["id"])
                if result and result.get("exists"):
                    st.success(f"✅ Cible valide ({result.get('followers', '?')} followers)")
                elif result:
                    st.error("❌ Cible introuvable sur Twitter")
                else:
                    st.error("❌ Erreur de vérification")

        with col2:
            if st.button("📥 Collecter", key=f"c_{target['id']}"):
                with st.spinner("Collecte des tweets..."):
                    success, msg, res = collect_tweets(target["id"])
                if success:
                    st.success(f"📥 {res.get('saved', 0)} nouveaux tweets collectés!")
                    st.rerun()
                else:
                    st.error(f"Erreur: {msg}")

        with col3:
            if st.button("🤖 Analyser", key=f"a_{target['id']}", type="primary"):
                with st.spinner("Analyse en cours (peut prendre 1-2 min)..."):
                    success, msg, res = analyze_tweets(target["id"])
                if success:
                    st.success(f"🤖 {res.get('analyzed', 0)} tweets analysés!")
                    st.rerun()
                else:
                    st.error(f"Erreur: {msg}")

        with col4:
            if st.button("📊 Dashboard", key=f"d_{target['id']}"):
                st.switch_page("pages/2_Dashboard.py")

        # --- Résumé rapide de l'analyse ---
        tweets = get_tweets(target["id"], 100)
        total_tweets = len(tweets)
        analyzed = [t for t in tweets if t.get("sentiment")]
        not_analyzed = total_tweets - len(analyzed)

        st.markdown(f"**📈 {total_tweets} tweets** | ✅ {len(analyzed)} analysés | ⏳ {not_analyzed} en attente")

        if analyzed:
            # Mini distribution des sentiments
            sentiment_counts = {}
            for t in analyzed:
                s = t.get("sentiment", "inconnu")
                sentiment_counts[s] = sentiment_counts.get(s, 0) + 1

            cols = st.columns(len(sentiment_counts))
            for i, (sent, count) in enumerate(sorted(sentiment_counts.items(), key=lambda x: -x[1])):
                emoji = EMOJIS.get(sent, "❓")
                pct = count / len(analyzed) * 100
                with cols[i]:
                    st.metric(f"{emoji} {sent}", f"{pct:.0f}%", f"{count} tweets")

        # --- Tableau des tweets ---
        if tweets:
            with st.expander(f"📝 Voir les tweets ({total_tweets})", expanded=False):
                # Préparer les données pour le tableau
                rows = []
                for t in tweets:
                    sent = t.get("sentiment")
                    conf = t.get("confidence", 0)
                    emoji = EMOJIS.get(sent, "⏳") if sent else "⏳"
                    rows.append({
                        "Sentiment": f"{emoji} {sent.upper() if sent else 'Non analysé'}",
                        "Confiance": f"{conf:.0%}" if conf else "-",
                        "Tweet": t["text"][:150],
                        "Auteur": t.get("author_username", "?"),
                    })

                df = pd.DataFrame(rows)
                st.dataframe(df, hide_index=True)
        else:
            st.info("Aucun tweet collecté. Cliquez sur 📥 Collecter pour récupérer des tweets.")
