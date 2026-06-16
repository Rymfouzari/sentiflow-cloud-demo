FROM python:3.11-slim

WORKDIR /app

# Installer les dépendances
RUN pip install streamlit plotly altair httpx pandas

# Copier le code frontend
COPY frontend/ frontend/

# Rendre le script exécutable
RUN chmod +x frontend/start.sh

# Exposer le port Streamlit
EXPOSE 8501

# Commande de démarrage avec attente API
CMD ["bash", "frontend/start.sh"]
