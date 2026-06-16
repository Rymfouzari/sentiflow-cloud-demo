import httpx
from backend.app.config import get_settings

settings = get_settings()


class TwitterService:
    def __init__(self):
        self.api_key = settings.twitter_api_key
        self.base_url = "https://api.twitterapi.io"

    def _headers(self):
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def search_tweets(self, query: str):
        """Recherche des tweets pour un hashtag ou une requête."""
        if not self.api_key:
            return {"error": "TWITTER_API_KEY manquante"}

        # Tracker l'usage
        try:
            import redis
            from backend.app.config import get_settings
            r = redis.from_url(get_settings().redis_url)
            r.incr("sentiflow:usage:twitter_calls")
        except Exception:
            pass

        url = f"{self.base_url}/twitter/tweet/advanced_search"
        params = {"query": query, "queryType": "Latest"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers(), params=params)

        if response.status_code >= 400:
            return {"error": response.text, "status": response.status_code}

        data = response.json()
        return {"tweets": data.get("tweets", data.get("data", [])), "raw": data}

    async def get_user_info(self, username: str):
        """Récupère les infos d'un compte."""
        if not self.api_key:
            return None

        username = username.lstrip("@")
        url = f"{self.base_url}/twitter/user/info"
        params = {"userName": username}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers(), params=params)

        if response.status_code >= 400:
            return None
        return response.json()

    async def get_user_tweets(self, username: str):
        """Récupère les tweets d'un compte."""
        if not self.api_key:
            return {"error": "TWITTER_API_KEY manquante"}

        username = username.lstrip("@")
        url = f"{self.base_url}/twitter/user/last_tweets"
        params = {"userName": username}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers(), params=params)

        if response.status_code >= 400:
            return {"error": response.text, "status": response.status_code}

        data = response.json()
        return {"tweets": data.get("tweets", data.get("data", [])), "raw": data}

    async def verify_hashtag(self, hashtag: str):
        """Vérifie si un hashtag retourne des tweets."""
        result = await self.search_tweets(hashtag)
        if "error" in result:
            return False
        tweets = result.get("tweets", [])
        return isinstance(tweets, list) and len(tweets) > 0


twitter_service = TwitterService()
