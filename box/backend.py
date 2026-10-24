"""Client for the NextStep backend on Cloud Run (the same API the Android app uses).

The box gets its own anonymous Firebase account, exactly like the app ("no login, ever"), and keeps
one persistent HTTPS connection open: reusing it saves a TLS handshake on every agent step.
"""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import certifi
import httpx

from .config import Config


class BackendError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"backend {status}: {body[:300]}")
        self.status = status


class Backend:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.http = httpx.Client(base_url=cfg.api_base_url, timeout=90.0, verify=certifi.where(),
                                 headers={"User-Agent": "nextstep-box/0.1"})
        self._identity_path = Path(cfg.state_dir) / "identity.json"
        self._identity: dict[str, Any] = self._load_identity()
        self._auth_lock = threading.Lock()  # warm() and the first request may both sign in

    # ---- auth (Firebase anonymous accounts, REST) ------------------------------------------

    def _load_identity(self) -> dict[str, Any]:
        try:
            return json.loads(self._identity_path.read_text())
        except (OSError, ValueError):
            return {}

    def _save_identity(self) -> None:
        self._identity_path.parent.mkdir(parents=True, exist_ok=True)
        self._identity_path.write_text(json.dumps(self._identity))
        os.chmod(self._identity_path, 0o600)

    def _firebase(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        r = httpx.post(f"{url}?key={self.cfg.firebase_api_key}", json=body, timeout=20.0, verify=certifi.where())
        if r.status_code != 200:
            raise BackendError(r.status_code, r.text)
        return r.json()

    def _token(self) -> str | None:
        if not self.cfg.firebase_api_key:
            return None  # local backend without auth: X-Device-Id is used instead
        with self._auth_lock:
            return self._token_locked()

    def _token_locked(self) -> str:
        ident = self._identity
        if not ident.get("refresh_token"):
            res = self._firebase("https://identitytoolkit.googleapis.com/v1/accounts:signUp", {"returnSecureToken": True})
            ident = {"uid": res["localId"], "id_token": res["idToken"], "refresh_token": res["refreshToken"],
                     "expires_at": time.time() + int(res.get("expiresIn", 3600)) - 120}
        elif time.time() >= ident.get("expires_at", 0):
            res = self._firebase("https://securetoken.googleapis.com/v1/token",
                                 {"grant_type": "refresh_token", "refresh_token": ident["refresh_token"]})
            ident.update(id_token=res["id_token"], refresh_token=res["refresh_token"],
                         expires_at=time.time() + int(res.get("expires_in", 3600)) - 120)
        else:
            return ident["id_token"]
        self._identity = ident
        self._save_identity()
        return ident["id_token"]

    # ---- API ---------------------------------------------------------------------------------

    def warm(self) -> None:
        """Wake Cloud Run (it scales to zero) and open the HTTPS connection while the box is still
        reading the screen, so the first real request doesn't pay a cold start."""
        def ping() -> None:
            try:
                self.http.get("/health", timeout=20.0)
                self._token()
            except Exception:  # noqa: BLE001 - best effort; the real request reports errors
                pass
        threading.Thread(target=ping, daemon=True).start()

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {}
        token = self._token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            headers["X-Device-Id"] = "nextstep-box-dev"
        r = self.http.post(path, json=body, headers=headers)
        if r.status_code == 401 and token:
            self._identity["expires_at"] = 0  # token rejected: refresh once and retry
            headers["Authorization"] = f"Bearer {self._token()}"
            r = self.http.post(path, json=body, headers=headers)
        if r.status_code >= 400:
            raise BackendError(r.status_code, r.text)
        return r.json()
