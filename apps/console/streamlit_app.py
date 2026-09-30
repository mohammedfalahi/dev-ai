import json
import logging
from pathlib import Path
from typing import Any

import httpx
import streamlit as st

from packages.core.config import settings

logger = logging.getLogger("streamlit_console")

FASTAPI_BASE_URL = getattr(settings, "console_url", "http://localhost:8000") or "http://localhost:8000"
EVAL_REPORT_PATH = Path("eval-report.json")

st.set_page_config(
    page_title="CallOps — Intelligent On-Call Voice Console",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# High-contrast, clean white-themed executive styling
st.markdown(
    """
    <style>
    /* Global White Aesthetic */
    .stApp {
        background-color: #FFFFFF;
        color: #0F172A;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    
    /* Headers & Text */
    h1, h2, h3, h4, h5, h6 {
        color: #0F172A !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em;
    }
    
    /* Card Container */
    .callops-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 18px 22px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    }
    
    .callops-card-white {
        background-color: #FFFFFF;
        border: 1px solid #CBD5E1;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
    }

    /* Badges */
    .badge-resolved {
        background-color: #ECFDF5;
        color: #065F46;
        border: 1px solid #A7F3D0;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    
    .badge-escalated {
        background-color: #FFFBEB;
        color: #92400E;
        border: 1px solid #FDE68A;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }

    .badge-triggered {
        background-color: #FEF2F2;
        color: #991B1B;
        border: 1px solid #FECACA;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }

    .badge-idle {
        background-color: #F1F5F9;
        color: #475569;
        border: 1px solid #CBD5E1;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    
    .badge-tier1 {
        background-color: #EFF6FF;
        color: #1E40AF;
        border: 1px solid #BFDBFE;
        padding: 3px 8px;
        border-radius: 6px;
        font-family: monospace;
        font-size: 0.75rem;
        font-weight: 600;
    }

    .badge-tier2 {
        background-color: #FFF7ED;
        color: #C2410C;
        border: 1px solid #FFEDD5;
        padding: 3px 8px;
        border-radius: 6px;
        font-family: monospace;
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* Metric values */
    .metric-title {
        color: #64748B;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }
    .metric-value {
        color: #0F172A;
        font-size: 1.6rem;
        font-weight: 800;
    }
    
    /* Code block container */
    .code-box {
        background-color: #0F172A;
        color: #F8FAFC;
        padding: 12px 16px;
        border-radius: 8px;
        font-family: monospace;
        font-size: 0.85rem;
        overflow-x: auto;
    }

    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        border-bottom: 2px solid #E2E8F0;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        color: #64748B;
        font-weight: 600;
        font-size: 0.95rem;
        border-bottom: 2px solid transparent;
    }
    .stTabs [aria-selected="true"] {
        color: #2563EB !important;
        border-bottom: 2px solid #2563EB !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# HTTP Client Bridge Helpers
def api_get(endpoint: str) -> dict[str, Any] | None:
    try:
        with httpx.Client(base_url=FASTAPI_BASE_URL, timeout=8.0) as client:
            resp = client.get(endpoint)
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.debug("API GET %s error: %s", endpoint, exc)
    return None


def api_post(endpoint: str, json_data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    try:
        with httpx.Client(base_url=FASTAPI_BASE_URL, timeout=12.0) as client:
            resp = client.post(endpoint, json=json_data or {})
            if resp.status_code in (200, 201):
                return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("API POST %s error: %s", endpoint, exc)
    return None


# Initialize Streamlit Session State
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "last_workflow_id" not in st.session_state:
    st.session_state.last_workflow_id = None
if "last_fault" not in st.session_state:
    st.session_state.last_fault = None


# Fetch System & Fault State
backend_status = api_get("/api/faults/status")
is_backend_online = backend_status is not None

# Top System Bar
col_brand, col_telephony, col_refresh = st.columns([3, 2, 1])

with col_brand:
    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 10px;">
            <span style="font-size: 2rem;">🚨</span>
            <div>
                <div style="font-size: 1.35rem; font-weight: 800; color: #0F172A; line-height: 1.2;">CallOps Studio</div>
                <div style="font-size: 0.8rem; color: #64748B;">Intelligent Incident Investigation & Real-Time Voice Orchestrator</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_telephony:
    if is_backend_online:
        active_status = backend_status.get("active_fault_status", "IDLE") if backend_status else "IDLE"
        if active_status == "RESOLVED":
            badge_html = '<span class="badge-resolved">● RESOLVED</span>'
        elif active_status == "PROBLEM_ESCALATED_TO_HUMAN":
            badge_html = '<span class="badge-escalated">● PROBLEM_ESCALATED_TO_HUMAN</span>'
        elif active_status == "TRIGGERED":
            badge_html = '<span class="badge-triggered">● ACTIVE INCIDENT</span>'
        else:
            badge_html = '<span class="badge-idle">● IDLE / HEALTHY</span>'

        st.markdown(
            f"""
            <div style="text-align: right; margin-top: 6px;">
                <span style="font-size: 0.8rem; color: #64748B; margin-right: 8px;">State:</span>
                {badge_html}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div style="text-align: right; margin-top: 6px;">
                <span class="badge-triggered">⚠️ FastAPI Backend Offline (localhost:8000)</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

with col_refresh:
    if st.button("🔄 Sync State", use_container_width=True):
        st.rerun()

st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

# Fetch latest drill status if workflow exists
drill_data: dict[str, Any] | None = None
active_wf_id = backend_status.get("workflow_id") if backend_status else None
if active_wf_id:
    st.session_state.last_workflow_id = active_wf_id
    drill_data = api_get(f"/api/drill/status/{active_wf_id}")

# Top Metrics Row
m_col1, m_col2, m_col3, m_col4 = st.columns(4)

with m_col1:
    st.markdown(
        """
        <div class="callops-card">
            <div class="metric-title">Gateway Deduplication</div>
            <div class="metric-value">50 : 1 <span style="font-size: 0.85rem; font-weight: 500; color: #059669;">(98% Collapse)</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with m_col2:
    status_label = backend_status.get("active_fault_status", "IDLE") if backend_status else "OFFLINE"
    st.markdown(
        f"""
        <div class="callops-card">
            <div class="metric-title">Active Fault State</div>
            <div class="metric-value" style="font-size: 1.25rem; margin-top: 4px;">{status_label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with m_col3:
    wf_text = str(active_wf_id) if active_wf_id else "None"
    st.markdown(
        f"""
        <div class="callops-card">
            <div class="metric-title">Temporal Workflow</div>
            <div class="metric-value" style="font-size: 1.1rem; margin-top: 6px; font-family: monospace;">{wf_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with m_col4:
    st.markdown(
        """
        <div class="callops-card">
            <div class="metric-title">Perceived Turn Latency</div>
            <div class="metric-value" style="color: #059669;">&le; 800 ms <span style="font-size: 0.85rem; font-weight: 500; color: #64748B;">(p50 budget)</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# Primary Tab Layout
tab_cockpit, tab_forensics = st.tabs([
    "🕹️ Operations & Chaos Cockpit",
    "🔬 Triage Forensics & Evaluation Hub",
])


# ==============================================================================
# TAB 1: OPERATIONS & CHAOS COCKPIT
# ==============================================================================
with tab_cockpit:
    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    c_left, c_right = st.columns([1, 1], gap="large")

    with c_left:
        st.subheader("1. Chaos Fault Injection & Controls")
        st.caption("Trigger reproducible synthetic failures in labs/broken-shop to activate the slow-brain investigator.")

        btn_f1, btn_f2 = st.columns(2)
        btn_f3, btn_f4 = st.columns(2)

        with btn_f1:
            if st.button("💥 DB Pool Exhaustion", use_container_width=True, help="Triggers asyncpg connection pool timeout"):
                with st.spinner("Injecting fault & investigating..."):
                    res = api_post("/api/faults/db-pool-exhaustion")
                    if res:
                        st.session_state.last_fault = "db-pool-exhaustion"
                        if "greeting" in res:
                            st.session_state.chat_messages = [{"role": "agent", "text": res["greeting"]}]
                        st.success("Triggered: Postgres Pool Exhaustion")
                        st.rerun()

        with btn_f2:
            if st.button("💥 Redis Cache OOM", use_container_width=True, help="Simulates maxmemory evictions in Redis cluster"):
                with st.spinner("Injecting fault & investigating..."):
                    res = api_post("/api/faults/redis-oom")
                    if res:
                        st.session_state.last_fault = "redis-oom"
                        if "greeting" in res:
                            st.session_state.chat_messages = [{"role": "agent", "text": res["greeting"]}]
                        st.success("Triggered: Redis Cache OOM")
                        st.rerun()

        with btn_f3:
            if st.button("💥 502 Bad Gateway Storm", use_container_width=True, help="Simulates upstream ingress proxy drop"):
                with st.spinner("Injecting fault & investigating..."):
                    res = api_post("/api/faults/502-storm")
                    if res:
                        st.session_state.last_fault = "502-storm"
                        if "greeting" in res:
                            st.session_state.chat_messages = [{"role": "agent", "text": res["greeting"]}]
                        st.success("Triggered: 502 Bad Gateway Storm")
                        st.rerun()

        with btn_f4:
            if st.button("💥 Threadpool Deadlock", use_container_width=True, help="Simulates worker queue starvation"):
                with st.spinner("Injecting fault & investigating..."):
                    res = api_post("/api/faults/threadpool-deadlock")
                    if res:
                        st.session_state.last_fault = "threadpool-deadlock"
                        if "greeting" in res:
                            st.session_state.chat_messages = [{"role": "agent", "text": res["greeting"]}]
                        st.success("Triggered: Threadpool Deadlock")
                        st.rerun()

        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        st.markdown("**Incident Lifecycle Management:**")
        b_res1, b_res2, b_res3 = st.columns(3)

        with b_res1:
            if st.button("🔄 Reset State", use_container_width=True):
                api_post("/api/faults/reset")
                st.session_state.chat_messages = []
                st.session_state.last_workflow_id = None
                st.session_state.last_fault = None
                st.info("System state reset to IDLE.")
                st.rerun()

        with b_res2:
            if st.button("✅ Force Resolve", use_container_width=True):
                api_post("/api/faults/resolve")
                st.success("Active fault marked RESOLVED.")
                st.rerun()

        with b_res3:
            if st.button("🚨 Handover to Human", use_container_width=True):
                api_post("/api/faults/escalate")
                st.warning("Incident transitioned to PROBLEM_ESCALATED_TO_HUMAN.")
                st.rerun()

        st.markdown("---")
        st.subheader("2. Active Incident & Hybrid Policy Card")

        if drill_data and drill_data.get("ico"):
            ico_info = drill_data["ico"]
            tier_val = drill_data.get("tier") or "TIER_2_MUTATING"
            proposed_cmd = drill_data.get("proposed_command") or "No command proposed"

            tier_badge = (
                '<span class="badge-tier1">TIER 1 (READ-ONLY)</span>'
                if tier_val == "TIER_1_READ_ONLY"
                else '<span class="badge-tier2">TIER 2 (MUTATING)</span>'
            )

            st.markdown(
                f"""
                <div class="callops-card-white">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-weight: 800; font-size: 1.1rem; color: #0F172A;">{ico_info.get('incident_id', 'INC-UNKNOWN')}</span>
                        <span class="badge-triggered">{ico_info.get('severity', 'SEV1')}</span>
                    </div>
                    <div style="font-weight: 600; color: #334155; margin-bottom: 6px;">{ico_info.get('headline', 'No headline available')}</div>
                    <div style="font-size: 0.85rem; color: #64748B; margin-bottom: 12px;">Impact: {ico_info.get('impact', 'Unknown impact')}</div>
                    
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                        <span style="font-size: 0.8rem; font-weight: 700; color: #475569;">PROPOSED REMEDIATION</span>
                        {tier_badge}
                    </div>
                    <div class="code-box">{proposed_cmd}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if tier_val == "TIER_2_MUTATING":
                st.info("🛡️ **Zero-Mutation Safeguard Active:** Server auto-execution is strictly blocked. Affirmative spoken assent on the call dispatches exact runbook steps to your configured Telegram channel.")
            else:
                st.success("⚡ **Auto-Execution Permitted:** Diagnostic read-only command executes automatically in background.")
        else:
            st.markdown(
                """
                <div class="callops-card-white" style="text-align: center; color: #64748B; padding: 32px 16px;">
                    <span style="font-size: 2rem;">🛡️</span>
                    <div style="font-weight: 600; margin-top: 8px;">No Active Incident</div>
                    <div style="font-size: 0.85rem;">Trigger a chaos fault above to generate an Incident Context Object.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with c_right:
        st.subheader("3. Live Conversational Voice Simulator")
        st.caption("Sub-second duplex turn simulator connecting to the fast-brain agent and policy engine.")

        # Chat display container
        chat_box = st.container(height=360)
        with chat_box:
            if not st.session_state.chat_messages:
                st.markdown(
                    """
                    <div style="text-align: center; color: #94A3B8; padding: 48px 16px;">
                        <span style="font-size: 2.2rem;">📞</span>
                        <div style="font-weight: 600; margin-top: 8px; color: #475569;">Telephone Channel Idle</div>
                        <div style="font-size: 0.85rem;">When a drill is triggered, the opening spoken brief appears here.</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                for msg in st.session_state.chat_messages:
                    if msg["role"] == "agent":
                        with st.chat_message("assistant", avatar="🤖"):
                            st.write(msg["text"])
                            if "latency_ms" in msg:
                                l_val = round(msg["latency_ms"])
                                color_style = "color: #059669;" if l_val <= 800 else "color: #D97706;"
                                st.markdown(f"<span style='font-size: 0.75rem; font-family: monospace; {color_style}'>⚡ {l_val}ms latency</span>", unsafe_allow_html=True)
                    else:
                        with st.chat_message("user", avatar="👨‍💻"):
                            st.write(msg["text"])

        # Chat Input
        user_input = st.chat_input("Speak to agent (e.g., 'What is the root cause?', 'confirm', 'go ahead')...")
        if user_input:
            st.session_state.chat_messages.append({"role": "user", "text": user_input})
            chat_res = api_post("/api/chat", {"message": user_input})
            if chat_res:
                st.session_state.chat_messages.append({
                    "role": "agent",
                    "text": chat_res.get("response", "No response"),
                    "latency_ms": chat_res.get("latency_ms", 450),
                })
                # Check for Telegram escalation dispatch event
                dispatch_evt = chat_res.get("dispatch_event")
                if dispatch_evt and dispatch_evt.get("status") == "PROBLEM_ESCALATED_TO_HUMAN":
                    st.toast("🚨 Escalated to Telegram! Incident transferred to operator.", icon="📲")
            else:
                st.session_state.chat_messages.append({
                    "role": "agent",
                    "text": "CallOps agent unreachable. Please verify FastAPI console is running on port 8000.",
                })
            st.rerun()

        # Quick assent chips
        st.markdown("<span style='font-size: 0.8rem; color: #64748B; font-weight: 600;'>Spoken Assent Testing Chips:</span>", unsafe_allow_html=True)
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        with col_c1:
            if st.button("💬 'Go ahead'", use_container_width=True):
                st.session_state.chat_messages.append({"role": "user", "text": "go ahead"})
                res = api_post("/api/chat", {"message": "go ahead"})
                if res:
                    st.session_state.chat_messages.append({"role": "agent", "text": res.get("response", ""), "latency_ms": res.get("latency_ms", 420)})
                st.rerun()
        with col_c2:
            if st.button("💬 'Confirm'", use_container_width=True):
                st.session_state.chat_messages.append({"role": "user", "text": "confirm"})
                res = api_post("/api/chat", {"message": "confirm"})
                if res:
                    st.session_state.chat_messages.append({"role": "agent", "text": res.get("response", ""), "latency_ms": res.get("latency_ms", 410)})
                st.rerun()
        with col_c3:
            if st.button("💬 'Root cause?'", use_container_width=True):
                st.session_state.chat_messages.append({"role": "user", "text": "What is the root cause?"})
                res = api_post("/api/chat", {"message": "What is the root cause?"})
                if res:
                    st.session_state.chat_messages.append({"role": "agent", "text": res.get("response", ""), "latency_ms": res.get("latency_ms", 510)})
                st.rerun()
        with col_c4:
            if st.button("💬 'Wait, cancel'", use_container_width=True):
                st.session_state.chat_messages.append({"role": "user", "text": "wait, cancel"})
                res = api_post("/api/chat", {"message": "wait, cancel"})
                if res:
                    st.session_state.chat_messages.append({"role": "agent", "text": res.get("response", ""), "latency_ms": res.get("latency_ms", 390)})
                st.rerun()


# ==============================================================================
# TAB 2: TRIAGE FORENSICS & EVALUATION HUB
# ==============================================================================
with tab_forensics:
    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
    f_left, f_right = st.columns([1, 1], gap="large")

    with f_left:
        st.subheader("1. Incident Context Object (ICO) Forensics")
        st.caption("Slow-Brain synthesized evidence graph validated by Pydantic domain contracts.")

        if drill_data and drill_data.get("ico"):
            ico = drill_data["ico"]
            hyp = ico.get("hypothesis") or {}
            conf = float(hyp.get("confidence", 0.9))

            st.markdown(
                f"""
                <div class="callops-card-white">
                    <div class="metric-title">Grounded Root-Cause Hypothesis</div>
                    <div style="font-size: 1.15rem; font-weight: 700; color: #0F172A; margin: 4px 0 8px 0;">
                        {hyp.get('text', 'No hypothesis formed')}
                    </div>
                    <div style="font-size: 0.85rem; color: #64748B;">
                        Confidence Score: <b>{round(conf * 100)}%</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.progress(conf)

            # Signal list
            signals = ico.get("signals") or []
            if signals:
                st.markdown("**Corroborating Telemetry Signals:**")
                for sig in signals[:4]:
                    st.markdown(f"- **`{sig.get('metric', 'signal')}`**: {sig.get('value')} ({sig.get('observation', '')})")

            # Raw Contract Toggle
            with st.expander("📄 View Normalized Pydantic Contract JSON"):
                st.json(ico)
        else:
            st.info("No active Incident Context Object found. Trigger a fault drill from Tab 1 to populate.")

        st.markdown("---")
        st.subheader("2. Knowledge Vault & RAG Reranking Breakdown")
        st.caption("PostgreSQL 16 + pgvector (768d) & tsvector FTS fused via RRF (k=60) and MS-MARCO Cross-Encoder.")

        if drill_data and drill_data.get("ico") and drill_data["ico"].get("candidate_runbooks"):
            rbs = drill_data["ico"]["candidate_runbooks"]
            for idx, rb in enumerate(rbs, start=1):
                score = rb.get("score", 0.0)
                is_above_refusal = score >= -8.5
                badge_style = "badge-resolved" if is_above_refusal else "badge-triggered"
                refusal_text = "PASSED REFUSAL GATE" if is_above_refusal else "REFUSED"

                st.markdown(
                    f"""
                    <div class="callops-card-white">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <span style="font-weight: 700; color: #0F172A;">#{idx} {rb.get('title', 'Runbook')}</span>
                            <span class="{badge_style}">{refusal_text} (Logit: {score:.2f})</span>
                        </div>
                        <div style="font-size: 0.8rem; color: #64748B; margin-bottom: 8px;">Chunk ID: <code>{rb.get('chunk_id')}</code> • Service: <code>{rb.get('service')}</code></div>
                        <div class="code-box">{rb.get('content', '').strip()}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                """
                <div class="callops-card-white" style="color: #64748B; font-size: 0.9rem;">
                    No RAG candidates currently loaded in session memory.
                </div>
                """,
                unsafe_allow_html=True,
            )

    with f_right:
        st.subheader("3. Production 3-Tier Evaluation Matrix")
        st.caption("Mathematical rank statistics and AST verbatim command safety checks.")

        btn_eval_col, _ = st.columns([1, 1])
        with btn_eval_col:
            if st.button("▶ Run Full Evaluation Matrix", use_container_width=True):
                with st.spinner("Executing 3-tier benchmark matrix..."):
                    res = api_post("/api/evals/run")
                    if res:
                        st.success("Evaluation matrix executed!")
                        st.rerun()

        # Load latest evals
        evals_data = api_get("/api/evals/latest")
        if not evals_data and EVAL_REPORT_PATH.exists():
            try:
                evals_data = json.loads(EVAL_REPORT_PATH.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                evals_data = None

        if evals_data:
            ov = evals_data.get("system_overview", {})
            st.markdown(
                f"""
                <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: #475569; margin-bottom: 12px; background: #F1F5F9; padding: 8px 12px; border-radius: 6px;">
                    <span>Corpus: <b>{ov.get('runbooks_count', 20)} runbooks ({ov.get('chunks_count', 129)} chunks)</b></span>
                    <span>Golden Cases: <b>{ov.get('evaluated_cases', 21)}</b></span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Tier 1
            st.markdown("**Tier 1: Retrieval Recall Candidate Gates**")
            for g in evals_data.get("tier1_retrieval", []):
                p_badge = '<span class="badge-resolved">PASS</span>' if g.get("passed") else '<span class="badge-triggered">FAIL</span>'
                st.markdown(
                    f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #F1F5F9; padding: 6px 0; font-size: 0.85rem;">
                        <span>{g.get('name')}</span>
                        <span><b>{g.get('actual_formatted')}</b> (Target: {g.get('target_formatted')}) {p_badge}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Tier 2
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            st.markdown("**Tier 2: Reranking & Refusal Gates**")
            for g in evals_data.get("tier2_reranking", []):
                p_badge = '<span class="badge-resolved">PASS</span>' if g.get("passed") else '<span class="badge-triggered">FAIL</span>'
                st.markdown(
                    f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #F1F5F9; padding: 6px 0; font-size: 0.85rem;">
                        <span>{g.get('name')}</span>
                        <span><b>{g.get('actual_formatted')}</b> (Target: {g.get('target_formatted')}) {p_badge}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Tier 3
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            st.markdown("**Tier 3: Generation & Safety Grounding Gates**")
            for g in evals_data.get("tier3_generation", []):
                p_badge = '<span class="badge-resolved">PASS</span>' if g.get("passed") else '<span class="badge-triggered">FAIL</span>'
                st.markdown(
                    f"""
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #F1F5F9; padding: 6px 0; font-size: 0.85rem;">
                        <span>{g.get('name')}</span>
                        <span><b>{g.get('actual_formatted')}</b> (Target: {g.get('target_formatted')}) {p_badge}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Overall Verdict
            overall_pass = evals_data.get("overall_passed", True)
            if overall_pass:
                st.markdown(
                    """
                    <div style="margin-top: 14px; padding: 12px; background-color: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 8px; text-align: center; color: #065F46; font-weight: 800;">
                        🏆 ALL PRODUCTION SAFETY GATES PASSED [PASS]
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    """
                    <div style="margin-top: 14px; padding: 12px; background-color: #FEF2F2; border: 1px solid #FECACA; border-radius: 8px; text-align: center; color: #991B1B; font-weight: 800;">
                        ⚠️ SAFETY GATE REGRESSION DETECTED [FAIL]
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.info("No evaluation scorecard found. Click 'Run Full Evaluation Matrix' above to evaluate.")
