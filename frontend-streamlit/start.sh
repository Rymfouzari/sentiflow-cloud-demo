#!/bin/bash
echo "Attente de l'API..."
until python -c "import httpx; httpx.get('http://api:8000/health')" 2>/dev/null; do
    echo "API pas prête, retry dans 3s..."
    sleep 3
done

# Résoudre l'IP de l'API pour éviter les problèmes DNS de Streamlit
IP=$(python -c "import socket; print(socket.gethostbyname('api'))")
export API_URL="http://${IP}:8000"
echo "API prête! URL=${API_URL}"

exec streamlit run frontend/app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true
