from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralized configuration for the On-call Voice system.
    Settings can be overridden by environment variables or a .env file.
    """
    # Database Configuration
    db_conn_str: str = "postgresql://callops:callops_dev@localhost:5432/callops"
    
    # Knowledge Vault Configuration
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    min_rerank_score: float = -8.5
    
    # Generative Model Configuration
    investigator_llm_model: str = "gemini-3.8-flash"
    voice_agent_llm_model: str = "gemini-3.8-flash"
    
    # Voice Pipeline Providers
    stt_provider: str = "deepgram"
    tts_provider: str = "google-tts"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
