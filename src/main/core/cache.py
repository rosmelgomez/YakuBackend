import time
import threading
from typing import Any, Callable, Optional
from functools import wraps

class MemoryCache:
    def __init__(self):
        self._cache: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            val, expires_at = entry
            if time.time() > expires_at:
                del self._cache[key]
                return None
            return val

    def set(self, key: str, value: Any, ttl_seconds: int = 30) -> None:
        with self._lock:
            expires_at = time.time() + ttl_seconds
            self._cache[key] = (value, expires_at)

    def invalidate(self, prefix: Optional[str] = None) -> None:
        with self._lock:
            if not prefix:
                self._cache.clear()
                return
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._cache[k]

    def cleanup(self) -> None:
        """Elimina entradas expiradas para mantener la memoria controlada."""
        now = time.time()
        with self._lock:
            keys_to_delete = [k for k, (_, expires_at) in self._cache.items() if now > expires_at]
            for k in keys_to_delete:
                del self._cache[k]

# Instancia global del caché en memoria para backend
backend_cache = MemoryCache()
