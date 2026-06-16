import asyncio
import sys
sys.path.insert(0, "/app")

from backend.app.services.rag import chat, get_vector_index
from backend.app.database import SessionLocal

async def test():
    db = SessionLocal()
    idx = get_vector_index()
    idx.is_fitted = False
    idx._last_indexed_count = 0
    idx.documents = []

    result = await chat(db, "quels sont les sentiments sur @BTS_twt ?", enable_mcp=True)
    print(f"MCP: {result.get('mcp_used')}")
    print(f"Tweets: {result.get('total_retrieved')}")
    print(f"Answer: {result.get('answer', '')[:500]}")
    db.close()

asyncio.run(test())
