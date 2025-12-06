import aioredis
import os

# Redis URL (update if your Redis server is remote or password-protected)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create a Redis client
redis = aioredis.from_url(REDIS_URL, decode_responses=True) 