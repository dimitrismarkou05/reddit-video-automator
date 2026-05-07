"""OAuth 2.0 flow for YouTube Data API."""

import json
import secrets
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from urllib.parse import urlencode

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from sqlalchemy.orm import Session

from backend.models import Setting
from backend.settings_manager import SettingsManager


YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
]

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"


class YouTubeAuthError(Exception):
    """Raised when OAuth flow or token operations fail."""
    pass


class YouTubeAuthManager:
    """Manages Google OAuth 2.0 for YouTube Data API."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = SettingsManager(db)
        self._credentials: Optional[Credentials] = None

    def _load_tokens(self) -> Optional[Dict[str, Any]]:
        """Load token blob from encrypted DB setting."""
        raw = self.settings.get("youtube_oauth_tokens", decrypt_value=True)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise YouTubeAuthError(f"Corrupted token storage: {exc}")

    def _save_tokens(self, tokens: Dict[str, Any]) -> None:
        """Persist token blob encrypted in DB."""
        self.settings.set(
            "youtube_oauth_tokens",
            json.dumps(tokens),
            encrypt_value=True,
        )

    def _delete_tokens(self) -> None:
        """Remove stored tokens (logout)."""
        token_setting = (
            self.db.query(Setting)
            .filter(Setting.key == "youtube_oauth_tokens")
            .first()
        )
        if token_setting:
            self.db.delete(token_setting)
            self.db.commit()

    def _get_client_config(self) -> Dict[str, str]:
        """Read client_id / client_secret from encrypted settings."""
        client_id = self.settings.get("youtube_client_id", decrypt_value=True)
        client_secret = self.settings.get("youtube_client_secret", decrypt_value=True)

        if not client_id or not client_secret:
            raise YouTubeAuthError(
                "YouTube OAuth credentials not configured. "
                "Set youtube_client_id and youtube_client_secret in Settings."
            )
        return {"client_id": client_id, "client_secret": client_secret}

    def is_configured(self) -> bool:
        """Return True if client_id and client_secret are stored."""
        try:
            self._get_client_config()
            return True
        except YouTubeAuthError:
            return False

    def is_authenticated(self) -> bool:
        """Return True if we have stored tokens that are (or can be) valid."""
        tokens = self._load_tokens()
        if not tokens:
            return False
        return bool(tokens.get("refresh_token"))

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """Fetch basic Google profile info for the logged-in user."""
        creds = self.get_credentials()
        if not creds or not creds.valid:
            return None

        try:
            resp = httpx.get(
                "https://www.googleapis.com/oauth2/v1/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise YouTubeAuthError(f"Failed to fetch user info: {exc}")

    def initiate_auth_flow(self, redirect_uri: str = "http://localhost:8080/callback") -> Dict[str, str]:
        """Start the OAuth consent flow and return the authorization URL."""
        config = self._get_client_config()
        state = secrets.token_urlsafe(32)
        self.settings.set("youtube_oauth_state", state, encrypt_value=True)

        params = {
            "client_id": config["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(YOUTUBE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
        return {"auth_url": auth_url, "state": state, "redirect_uri": redirect_uri}

    def exchange_code(
        self,
        code: str,
        state: str,
        redirect_uri: str = "http://localhost:8080/callback",
    ) -> Credentials:
        """Exchange the authorization code for access/refresh tokens."""
        stored_state = self.settings.get("youtube_oauth_state", decrypt_value=True)
        if not stored_state or stored_state != state:
            raise YouTubeAuthError("Invalid OAuth state parameter. Possible CSRF attack.")

        config = self._get_client_config()

        data = {
            "code": code,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        try:
            resp = httpx.post(GOOGLE_TOKEN_URL, data=data, timeout=30)
            resp.raise_for_status()
            token_response = resp.json()
        except httpx.HTTPError as exc:
            raise YouTubeAuthError(f"Token exchange failed: {exc}")

        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        expires_in = token_response.get("expires_in", 3600)
        token_type = token_response.get("token_type", "Bearer")

        if not access_token:
            raise YouTubeAuthError(f"No access_token in response: {token_response}")

        expiry = datetime.now(timezone.utc).timestamp() + expires_in

        self._save_tokens({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_uri": GOOGLE_TOKEN_URL,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "scopes": YOUTUBE_SCOPES,
            "expiry": expiry,
            "token_type": token_type,
        })

        self._credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=GOOGLE_TOKEN_URL,
            client_id=config["client_id"],
            client_secret=config["client_secret"],
            scopes=YOUTUBE_SCOPES,
        )

        return self._credentials

    def get_credentials(self) -> Optional[Credentials]:
        """Return valid credentials, refreshing if necessary."""
        if self._credentials and self._credentials.valid:
            return self._credentials

        tokens = self._load_tokens()
        if not tokens:
            return None

        creds = Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=tokens.get("token_uri", GOOGLE_TOKEN_URL),
            client_id=tokens.get("client_id"),
            client_secret=tokens.get("client_secret"),
            scopes=tokens.get("scopes", YOUTUBE_SCOPES),
        )

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as exc:
                    raise YouTubeAuthError(f"Token refresh failed: {exc}")

                self._save_tokens({
                    "access_token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_uri": creds.token_uri,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "scopes": list(creds.scopes) if creds.scopes else YOUTUBE_SCOPES,
                    "expiry": creds.expiry.timestamp() if creds.expiry else None,
                    "token_type": "Bearer",
                })
            else:
                raise YouTubeAuthError(
                    "Credentials expired and no refresh token available. "
                    "Please re-authenticate."
                )

        self._credentials = creds
        return creds

    def build_service(self):
        """Build and return a googleapiclient build('youtube', 'v3') service."""
        from googleapiclient.discovery import build

        creds = self.get_credentials()
        if not creds:
            raise YouTubeAuthError("Not authenticated. Call initiate_auth_flow() first.")

        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    def logout(self) -> None:
        """Revoke the current token and clear local storage."""
        tokens = self._load_tokens()
        if tokens and tokens.get("access_token"):
            try:
                httpx.post(
                    GOOGLE_REVOKE_URL,
                    params={"token": tokens["access_token"]},
                    timeout=10,
                )
            except Exception:
                pass

        self._delete_tokens()
        self._credentials = None
