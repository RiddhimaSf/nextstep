import httpx
import time
import hashlib
import json
from agent.runtime import ToolResult


def idempotency_key(user_id: str, action: str, payload: dict) -> str:
    raw = json.dumps({"u": user_id, "a": action, "p": payload}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class ResilientClient:
    def __init__(self, base_url: str, token: str, timeout: float = 15.0, max_attempts: int = 4):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {token}"}
        self.timeout = timeout
        self.max_attempts = max_attempts

    def request(self, method: str, path: str, **kwargs) -> ToolResult:
        for attempt in range(self.max_attempts):
            try:
                with httpx.Client(timeout=self.timeout) as c:
                    r = c.request(method, f"{self.base_url}{path}", headers=self.headers, **kwargs)

                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                if r.status_code == 401:
                    return ToolResult(False, error_code="AUTH")
                if r.status_code == 404:
                    return ToolResult(False, error_code="NOT_FOUND")
                if r.status_code >= 400:
                    return ToolResult(False, error_code="VALIDATION", data=r.text[:500])
                return ToolResult(True, data=r.json() if r.content else None)
            except httpx.TimeoutException:
                if attempt == self.max_attempts - 1:
                    return ToolResult(False, error_code="TIMEOUT")
                time.sleep(0.5 * (2 ** attempt))
            except httpx.HTTPError as e:
                return ToolResult(False, error_code="NETWORK", data=str(e))

        return ToolResult(False, error_code="RATE_LIMIT")