"""
Observability package for CallOps / On-call Voice.
Provides safe, scrubbed, non-blocking Langfuse tracing and metrics.
"""

from packages.observability.redaction import (
    is_sensitive_key,
    scrub_sensitive_data,
    scrub_string,
)
from packages.observability.tracing import (
    flush_tracing,
    get_langfuse_client,
    is_langfuse_enabled,
    observe,
    record_score,
    shutdown_tracing,
    trace_span,
    update_current_generation,
    update_current_span,
)

__all__ = [
    "flush_tracing",
    "get_langfuse_client",
    "is_langfuse_enabled",
    "is_sensitive_key",
    "observe",
    "record_score",
    "scrub_sensitive_data",
    "scrub_string",
    "shutdown_tracing",
    "trace_span",
    "update_current_generation",
    "update_current_span",
]
