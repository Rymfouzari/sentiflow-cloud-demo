import streamlit as st
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from components.api import get_headers, API_URL, get_targets, get_tweets
import httpx

st.title("⚙️ Administration")

if not st.session_state.get("token"):
    st.warning("Veuillez vous connecter")
    st.stop()

if not st.session_state.get("user", {}).get("is_admin", False):
    st.error("🚫 Acces reserve aux administrateurs")
    st.stop()

st.success(f"👑 Admin: **{st.session_state.user['username']}**")

# Stats
st.subheader("📊 Statistiques")
try:
    response = httpx.get(f"{API_URL}/admin/stats", headers=get_headers())
    if response.status_code == 200:
        stats = response.json()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Utilisateurs", stats.get("users", 0))
        col2.metric("Cibles", stats.get("targets", 0))
        col3.metric("Tweets", stats.get("tweets", 0))
        col4.metric("Alertes", stats.get("alerts", 0))
except:
    st.info("Stats non disponibles")

st.divider()

# Apercu des tweets par cible
st.subheader("📝 Apercu des tweets")
targets = get_targets()

if targets:
    target_options = {t["id"]: f"{t['name']} ({t['target_type']})" for t in targets}
    selected_target = st.selectbox(
        "Selectionner une cible", 
        options=list(target_options.keys()), 
        format_func=lambda x: target_options[x]
    )
    
    tweets = get_tweets(selected_target, 50)
    
    if tweets:
        # Stats des sentiments
        sentiments = {}
        for t in tweets:
            s = t.get("sentiment", "non_analyse")
            sentiments[s] = sentiments.get(s, 0) + 1
        
        st.write("**Distribution des sentiments:**")
        cols = st.columns(len(sentiments))
        emojis = {"joie":"😊","tristesse":"😢","colere":"😠","peur":"😨","surprise":"😲","amour":"❤️","non_analyse":"⏳"}
        for i, (sent, count) in enumerate(sentiments.items()):
            with cols[i]:
                emoji = emojis.get(sent, "❓")
                st.metric(f"{emoji} {sent}", count)
        
        st.divider()
        
        # Liste des tweets
        for tweet in tweets:
            sent = tweet.get("sentiment")
            conf = tweet.get("confidence", 0)
            
            col1, col2 = st.columns([4, 1])
            with col1:
                if sent:
                    emoji = emojis.get(sent, "❓")
                    st.markdown(f"**{emoji} {sent.upper()}** ({conf:.0%}) - @{tweet.get('author_username', '?')}")
                else:
                    st.markdown(f"⏳ Non analyse - @{tweet.get('author_username', '?')}")
                st.caption(tweet['text'][:300])
            with col2:
                st.caption(f"ID: {tweet['id']}")
            st.divider()
    else:
        st.info("Aucun tweet pour cette cible")
else:
    st.info("Aucune cible")

st.divider()

# Gestion des utilisateurs
st.subheader("👥 Gestion des utilisateurs")
try:
    response = httpx.get(f"{API_URL}/admin/users", headers=get_headers())
    if response.status_code == 200:
        users = response.json()
        for user in users:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                role = "👑 Admin" if user["is_admin"] else "👤 User"
                st.write(f"{role} - **{user['username']}** ({user['email']})")
            with col2:
                if user["id"] != st.session_state.user["id"]:
                    btn_label = "Retrograder" if user["is_admin"] else "Promouvoir"
                    if st.button(btn_label, key=f"toggle_{user['id']}"):
                        resp = httpx.patch(
                            f"{API_URL}/admin/users/{user['id']}/toggle-admin", 
                            headers=get_headers()
                        )
                        if resp.status_code == 200:
                            st.rerun()
except Exception as e:
    st.error(f"Erreur: {e}")

st.divider()

# Supprimer tweets
st.subheader("🗑️ Supprimer les tweets")
if targets:
    del_target = st.selectbox(
        "Cible a nettoyer", 
        options=list(target_options.keys()), 
        format_func=lambda x: target_options[x],
        key="del_select"
    )
    
    if st.button("🗑️ Supprimer tous les tweets de cette cible", type="secondary"):
        response = httpx.delete(
            f"{API_URL}/admin/tweets/{del_target}", 
            headers=get_headers()
        )
        if response.status_code == 200:
            result = response.json()
            st.success(f"✅ {result['deleted']} tweets supprimes")
            st.rerun()

st.divider()

# Zone dangereuse
st.subheader("⚠️ Zone dangereuse")
with st.expander("Supprimer TOUTES les donnees"):
    st.warning("Cette action est irreversible!")
    confirm = st.text_input("Tapez 'SUPPRIMER' pour confirmer")
    if st.button("🗑️ Supprimer TOUS les tweets", type="primary", disabled=confirm != "SUPPRIMER"):
        response = httpx.delete(f"{API_URL}/admin/tweets/all", headers=get_headers())
        if response.status_code == 200:
            result = response.json()
            st.success(f"✅ {result['deleted']} tweets supprimes")
