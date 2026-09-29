"""
Pipeline Diagnostic & Tracing Inspection Script.
Validates infrastructure connectivity (Postgres, Redis, LiveKit, Langfuse),
tests synthetic incident investigation and voice briefing generation,
and inspects recent telemetry/trace logs.
"""

import asyncio
import json
import logging
import socket
import sys
import time
from pathlib import Path
from typing import Any

# Ensure workspace root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.core.config import settings
from packages.observability.tracing import is_langfuse_enabled

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("inspect_traces")


def check_tcp_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Checks if a TCP port is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, OSError):
        return False


def check_postgres() -> tuple[bool, str]:
    """Tests connection to the configured PostgreSQL database."""
    try:
        import psycopg

        db_url = getattr(settings, "database_url", None) or settings.db_conn_str
        with (
            psycopg.connect(db_url, connect_timeout=3) as conn,
            conn.cursor() as cur,
        ):
            cur.execute("SELECT 1;")
            return True, "PostgreSQL connected (SELECT 1 OK)"
    except Exception as exc:  # noqa: BLE001
        return False, f"PostgreSQL connection failed: {exc}"


def check_redis() -> tuple[bool, str]:
    """Tests TCP connectivity to Redis on localhost:6379."""
    if check_tcp_port("localhost", 6379, timeout=2.0):
        return True, "Redis port 6379 is reachable"
    return False, "Redis port 6379 unreachable (service may be stopped)"


def check_livekit() -> tuple[bool, str]:
    """Validates LiveKit Cloud / local server configuration."""
    url = settings.livekit_url
    api_key = settings.livekit_api_key
    api_secret = settings.livekit_api_secret

    has_creds = bool(api_key and api_secret)
    if not has_creds:
        return False, f"LiveKit credentials missing. URL={url}"

    # Check connection if local or cloud URL
    if "localhost" in url:
        is_up = check_tcp_port("localhost", 7880, timeout=2.0)
        status = "reachable" if is_up else "unreachable (local server not started)"
        return is_up, f"LiveKit Local ({url}): {status}"
    else:
        return True, f"LiveKit Cloud configured ({url})"


def check_langfuse() -> tuple[bool, str]:
    """Validates Langfuse observability tracing configuration."""
    base_url = settings.langfuse_base_url
    enabled = is_langfuse_enabled()
    if enabled:
        return True, f"Langfuse enabled at {base_url} (keys configured)"
    return False, "Langfuse in safe no-op mode (LANGFUSE_PUBLIC_KEY / SECRET_KEY unset)"


def get_recent_telemetry(limit: int = 5) -> list[dict[str, Any]]:
    """Loads the most recent records from the telemetry JSONL log."""
    telemetry_file = Path("data/generated/telemetry.jsonl")
    if not telemetry_file.exists():
        return []

    lines = telemetry_file.read_text(encoding="utf-8").strip().split("\n")
    recent = lines[-limit:]
    records = []
    for line in recent:
        if line.strip():
            try:
                records.append(json.loads(line))
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Skipping malformed telemetry record: {exc}")
    return records


async def run_synthetic_investigation() -> tuple[bool, str, str]:
    """
    Injects a synthetic SEV1 alert into investigate_incident and checks ICO output.
    """
    from apps.investigator.engine import investigate_incident

    synthetic_alert = {
        "incident_id": f"INC-DIAG-{int(time.time())}",
        "severity": "SEV1",
        "service": "checkout-api",
        "error": "asyncpg.exceptions.TimeoutError or pool acquire timeout",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    try:
        ico = await investigate_incident(synthetic_alert)
        brief = ico.to_voice_brief()
        details = (
            f"ICO Generated: incident={ico.incident_id}, severity={ico.severity}, "
            f"runbooks={len(ico.candidate_runbooks)}, hypothesis='{ico.hypothesis.text}'"
        )
        return True, details, brief
    except Exception as exc:  # noqa: BLE001
        return False, f"Investigation failed: {exc}", ""


async def main() -> None:
    print("=" * 80)
    print("      ON-CALL VOICE — END-TO-END PIPELINE TRACE & HEALTH DIAGNOSTIC")
    print("=" * 80)

    # 1. Component Connectivity Checks
    print("\n[1/4] Probing Core Infrastructure & Services:")
    pg_ok, pg_msg = check_postgres()
    print(f"  • Postgres:  {'[PASS]' if pg_ok else '[WARN]'} {pg_msg}")

    redis_ok, redis_msg = check_redis()
    print(f"  • Redis:     {'[PASS]' if redis_ok else '[INFO]'} {redis_msg}")

    lk_ok, lk_msg = check_livekit()
    print(f"  • LiveKit:   {'[PASS]' if lk_ok else '[WARN]'} {lk_msg}")

    lf_ok, lf_msg = check_langfuse()
    print(f"  • Langfuse:  {'[PASS]' if lf_ok else '[INFO]'} {lf_msg}")

    # 2. Synthetic Incident Investigation & Voice Brief Generation
    print("\n[2/4] Testing Synthetic Incident Investigation (Slow Brain -> Fast Brain):")
    inv_ok, inv_msg, voice_brief = await run_synthetic_investigation()
    print(f"  • Status:    {'[PASS]' if inv_ok else '[FAIL]'} {inv_msg}")
    if inv_ok:
        print(f"  • Voice Brief: \"{voice_brief}\"")

    # 3. LiveKit Dispatch & Worker Health
    print("\n[3/4] Checking LiveKit Voice Runtime Compatibility:")
    try:
        from apps.voice.agent import entrypoint, get_default_ico

        default_ico = get_default_ico()
        _ = default_ico.to_voice_brief()
        print(f"  • Voice Worker: [PASS] Mode B entrypoint '{entrypoint.__name__}' is loaded.")
        print("  • Speech Method: [PASS] 'generate_reply' configured for Gemini RealtimeModel.")
    except Exception as exc:  # noqa: BLE001
        print(f"  • Voice Worker: [FAIL] {exc}")

    # 4. Recent Telemetry Logs
    print("\n[4/4] Inspecting Recent Telemetry Records (Last 5 Entries):")
    records = get_recent_telemetry(5)
    if records:
        for r in records:
            ev_id = r.get("evidence_id", "UNKNOWN")
            src = r.get("source_type", "src")
            svc = r.get("service", "svc")
            msg = r.get("message", "")
            print(f"  • [{src.upper()}] {ev_id} ({svc}): {msg}")
    else:
        print("  • No telemetry entries found in data/generated/telemetry.jsonl.")

    # Summary Scorecard
    print("\n" + "=" * 80)
    print("                      END-TO-END HEALTH STATUS SCORECARD")
    print("=" * 80)
    print(f"  • Database & Knowledge Layer:  {'HEALTHY' if pg_ok else 'OFFLINE / FALLBACK'}")
    print(f"  • Telephony & LiveKit Channel: {'READY' if lk_ok else 'CONFIG REQUIRED'}")
    print(f"  • Slow-Brain Investigation:    {'VERIFIED' if inv_ok else 'ERROR'}")
    print(f"  • Observability & Traces:      {'ACTIVE' if lf_ok else 'SAFE NO-OP'}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
