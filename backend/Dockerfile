# Stage 1: Build le frontend React
FROM node:18-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/public/ public/
COPY frontend/src/ src/
ENV REACT_APP_API_URL=""
RUN npm run build

# Stage 2: API Python + frontend buildé
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install uv && uv pip install --system -e .

COPY backend/ backend/
COPY services/ services/
COPY scripts/ scripts/

# Copier le frontend buildé depuis le stage 1
COPY --from=frontend-build /frontend/build frontend_build/

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
