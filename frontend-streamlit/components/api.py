import httpx
import streamlit as st
from typing import Optional
import os

API_URL = os.getenv("API_URL", "http://localhost:8000")


def get_headers() -> dict:
    if st.session_state.get("token"):
        return {"Authorization": f"Bearer {st.session_state.token}"}
    return {}


def login(email: str, password: str) -> tuple[bool, str, Optional[dict]]:
    try:
        r = httpx.post(f"{API_URL}/auth/login", json={"email": email, "password": password})
        if r.status_code == 200:
            return True, "Connexion reussie", r.json()
        return False, "Email ou mot de passe incorrect", None
    except Exception as e:
        return False, str(e), None


def register(email: str, username: str, password: str) -> tuple[bool, str]:
    try:
        r = httpx.post(f"{API_URL}/auth/register", json={
            "email": email, "username": username, "password": password
        })
        if r.status_code == 201:
            return True, "Inscription reussie!"
        return False, r.json().get("detail", "Erreur")
    except Exception as e:
        return False, str(e)


def get_me() -> Optional[dict]:
    try:
        r = httpx.get(f"{API_URL}/auth/me", headers=get_headers())
        if r.status_code == 200:
            return r.json()
        return None
    except:
        return None


def get_targets() -> list:
    try:
        r = httpx.get(f"{API_URL}/targets/", headers=get_headers())
        if r.status_code == 200:
            return r.json()
        return []
    except:
        return []


def create_target(name: str, target_type: str) -> Optional[dict]:
    try:
        r = httpx.post(f"{API_URL}/targets/", headers=get_headers(), json={
            "name": name, "target_type": target_type
        })
        if r.status_code == 201:
            return r.json()
        return None
    except:
        return None


def delete_target(target_id: int) -> bool:
    try:
        r = httpx.delete(f"{API_URL}/targets/{target_id}", headers=get_headers())
        return r.status_code == 204
    except:
        return False


def verify_target(target_id: int) -> Optional[dict]:
    try:
        r = httpx.get(f"{API_URL}/twitter/verify/{target_id}", headers=get_headers(), timeout=30.0)
        if r.status_code == 200:
            return r.json()
        return None
    except:
        return None


def collect_tweets(target_id: int) -> tuple[bool, str, Optional[dict]]:
    try:
        r = httpx.post(f"{API_URL}/twitter/collect/{target_id}", headers=get_headers(), timeout=30.0)
        if r.status_code == 200:
            return True, "OK", r.json()
        return False, r.json().get("detail", "Erreur"), None
    except Exception as e:
        return False, str(e), None


def analyze_tweets(target_id: int) -> tuple[bool, str, Optional[dict]]:
    try:
        r = httpx.post(f"{API_URL}/analysis/{target_id}/analyze", headers=get_headers(), timeout=120.0)
        if r.status_code == 200:
            return True, "OK", r.json()
        return False, r.json().get("detail", "Erreur"), None
    except Exception as e:
        return False, str(e), None


def get_tweets(target_id: int, limit: int = 50) -> list:
    try:
        r = httpx.get(f"{API_URL}/tweets/{target_id}", headers=get_headers(), params={"limit": limit})
        if r.status_code == 200:
            return r.json()
        return []
    except:
        return []


def get_analysis(target_id: int, days: int = 7) -> Optional[dict]:
    try:
        r = httpx.get(f"{API_URL}/analysis/{target_id}", headers=get_headers(), params={"days": days})
        if r.status_code == 200:
            return r.json()
        return None
    except:
        return None


def get_alerts() -> list:
    try:
        r = httpx.get(f"{API_URL}/alerts/", headers=get_headers())
        if r.status_code == 200:
            return r.json()
        return []
    except:
        return []


def create_alert(target_id: int, name: str, sentiment: str, threshold: float, is_above: bool) -> Optional[dict]:
    try:
        r = httpx.post(f"{API_URL}/alerts/", headers=get_headers(), json={
            "target_id": target_id, "name": name, "sentiment": sentiment,
            "threshold": threshold, "is_above": is_above
        })
        if r.status_code == 201:
            return r.json()
        return None
    except:
        return None
