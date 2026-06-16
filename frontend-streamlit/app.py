import streamlit as st

st.set_page_config(
    page_title="SentiFlow",
    page_icon="📊",
    layout="wide"
)

# Init session state
if "token" not in st.session_state:
    st.session_state.token = None
if "user" not in st.session_state:
    st.session_state.user = None


def logout():
    st.session_state.token = None
    st.session_state.user = None


# Sidebar - Afficher statut connexion et navigation
with st.sidebar:
    if st.session_state.token:
        st.success(f"👤 {st.session_state.user['username']}")
        if st.session_state.user.get('is_admin'):
            st.caption("👑 Admin")
        if st.button("🚪 Déconnexion", use_container_width=True):
            logout()
            st.rerun()
        st.divider()
        
        # Navigation pour utilisateurs connectés
        st.page_link("app.py", label="Accueil", icon="🏠")
        st.page_link("pages/2_Dashboard.py", label="Dashboard", icon="📊")
        st.page_link("pages/3_Cibles.py", label="Cibles", icon="🎯")
        st.page_link("pages/4_Alertes.py", label="Alertes", icon="🔔")
        if st.session_state.user.get('is_admin'):
            st.page_link("pages/5_Admin.py", label="Admin", icon="⚙️")
    else:
        # Navigation pour utilisateurs non connectés
        st.page_link("app.py", label="Accueil", icon="🏠")
        st.page_link("pages/1_Login.py", label="Connexion", icon="🔐")


def main():
    st.title("📊 SentiFlow")
    st.subheader("Analyse de sentiments Twitter en temps réel")
    
    if st.session_state.token is None:
        st.info("Connectez-vous pour accéder au dashboard")
        st.page_link("pages/1_Login.py", label="Se connecter", icon="🔐")
    else:
        st.write(f"Bienvenue **{st.session_state.user['username']}** !")
        
        st.divider()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.page_link("pages/2_Dashboard.py", label="Dashboard", icon="📊")
        with col2:
            st.page_link("pages/3_Cibles.py", label="Gérer les cibles", icon="🎯")
        with col3:
            st.page_link("pages/4_Alertes.py", label="Alertes", icon="🔔")


if __name__ == "__main__":
    main()
