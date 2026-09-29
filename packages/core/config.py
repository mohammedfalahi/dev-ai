import json
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized configuration for the On-call Voice system.
    Settings can be overridden by environment variables or a .env file.
    """
    # Database Configuration
    db_conn_str: str = "postgresql://callops:callops_dev@localhost:5432/callops"
    database_url: str = "postgresql://callops:callops_dev@localhost:5432/callops"
    
    # Knowledge Vault Configuration
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    min_rerank_score: float = -8.5
    
    # Generative Model Configuration
    investigator_llm_model: str = "gemini-3.5-flash-lite"
    voice_agent_llm_model: str = "gemini-3.5-flash-lite"
    
    # Voice Pipeline Providers (Cascaded Legacy & LiveKit Gemini Live)
    stt_provider: str = "deepgram"
    tts_provider: str = "google-tts"
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"
    gemini_api_key: str | None = None
    gemini_live_model: str = "gemini-3.8-live"
    fallback_gemini_live_model: str = "gemini-live-2.5-flash-native-audio"
    google_cloud_project: str | None = None
    google_cloud_location: str = "us-central1"
    gemini_live_voice: str = "Puck"

    # Gateway & Ingest Configuration
    hmac_secret: str = "dev-secret-key-1234"
    grouping_window_seconds: int = 60
    temporal_host: str = "localhost:7233"
    console_url: str = "http://localhost:8000"

    # Observability & Langfuse Configuration
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # Telephony Configuration & Safety Guardrails
    telephony_mode: str = "twilio"  # Options: "twilio", "mock", "disabled"
    telephony_kill_switch: bool = False
    telephony_allowlist: Any = ["+919567245034"]
    max_calls_per_hour: int = 10
    recording_enabled: bool = False
    oncall_phone_number: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None
    twilio_twiml_url: str | None = None

    @field_validator("telephony_allowlist", mode="before")
    @classmethod
    def parse_allowlist(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [str(x).strip() for x in v]
        if isinstance(v, str):
            v_str = v.strip()
            if v_str.startswith("[") and v_str.endswith("]"):
                try:
                    parsed = json.loads(v_str)
                    if isinstance(parsed, list):
                        return [str(x).strip() for x in parsed]
                except (json.JSONDecodeError, ValueError):
                    return [part.strip().strip("'\"") for part in v_str.strip("[]").split(",") if part.strip().strip("'\"")]
            # Comma-separated or single raw number string
            return [part.strip().strip("'\"") for part in v_str.split(",") if part.strip().strip("'\"")]
        return ["+15555550100", "+15555550199"]

    @model_validator(mode="after")
    def ensure_oncall_number_in_allowlist(self) -> "Settings":
        if self.oncall_phone_number:
            norm = self.oncall_phone_number.strip()
            if isinstance(self.telephony_allowlist, list) and norm not in self.telephony_allowlist:
                self.telephony_allowlist.append(norm)
        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
