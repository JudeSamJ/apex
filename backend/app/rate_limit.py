from fastapi import Request, HTTPException
import time
from collections import defaultdict
from typing import Dict, List

# Sliding window cache: key -> list of timestamps
_request_history: Dict[str, List[float]] = defaultdict(list)

def check_rate_limit(user_id: str, endpoint: str, limit: int = 10, window_seconds: int = 60):
    """
    In-memory sliding window rate limiter.
    Raises HTTPException 429 if the user exceeds `limit` requests in the last `window_seconds`.
    """
    now = time.time()
    key = f"{user_id}:{endpoint}"
    
    # Filter out timestamps outside the active window
    cutoff = now - window_seconds
    _request_history[key] = [t for t in _request_history[key] if t > cutoff]
    
    if len(_request_history[key]) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait before executing further state modifications."
        )
        
    _request_history[key].append(now)
