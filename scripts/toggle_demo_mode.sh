#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Helper to toggle or set TELEPHONY_MODE in .env
# Usage:
#   ./scripts/toggle_demo_mode.sh               # Toggles between livekit-rtc and twilio
#   ./scripts/toggle_demo_mode.sh livekit-rtc   # Sets to livekit-rtc (demo / browser)
#   ./scripts/toggle_demo_mode.sh twilio        # Sets to twilio (PSTN outbound)
#   ./scripts/toggle_demo_mode.sh fake          # Sets to fake (CI / hermetic test)
# ==============================================================================

ENV_FILE=".env"

if [ ! -f "$ENV_FILE" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example "$ENV_FILE"
        echo "[+] Initialized .env from .env.example"
    else
        echo "[-] Error: .env file not found." >&2
        exit 1
    fi
fi

TARGET_MODE="${1:-}"

# Read current mode without exposing entire .env
CURRENT_MODE=$(grep -E '^TELEPHONY_MODE=' "$ENV_FILE" | head -n 1 | cut -d '=' -f2 | tr -d '"'\'' ')

if [ -z "$TARGET_MODE" ]; then
    if [ "$CURRENT_MODE" = "livekit-rtc" ]; then
        TARGET_MODE="twilio"
    else
        TARGET_MODE="livekit-rtc"
    fi
fi

# Normalize target mode
case "$TARGET_MODE" in
    livekit-rtc|browser)
        NORMALIZED_MODE="livekit-rtc"
        ;;
    twilio)
        NORMALIZED_MODE="twilio"
        ;;
    fake)
        NORMALIZED_MODE="fake"
        ;;
    livekit-sip|livekit_sip)
        NORMALIZED_MODE="livekit-sip"
        ;;
    *)
        echo "[-] Invalid mode: $TARGET_MODE" >&2
        echo "    Allowed: livekit-rtc, twilio, fake, livekit-sip" >&2
        exit 1
        ;;
esac

# Update .env in-place safely using python to avoid sed -i OS incompatibilities
python3 -c "
from pathlib import Path
p = Path('$ENV_FILE')
lines = p.read_text().splitlines()
found = False
new_lines = []
for line in lines:
    if line.startswith('TELEPHONY_MODE='):
        new_lines.append('TELEPHONY_MODE=\"$NORMALIZED_MODE\"')
        found = True
    else:
        new_lines.append(line)
if not found:
    new_lines.append('TELEPHONY_MODE=\"$NORMALIZED_MODE\"')
p.write_text('\n'.join(new_lines) + '\n')
"

echo "[✓] TELEPHONY_MODE updated from '${CURRENT_MODE:-none}' to '$NORMALIZED_MODE'"
if [ "$NORMALIZED_MODE" = "livekit-rtc" ]; then
    echo "    Mode: LiveKit RTC (Demo / Browser Mode). Outbound PSTN is bypassed."
    echo "    Browser: https://agents-playground.livekit.io"
elif [ "$NORMALIZED_MODE" = "twilio" ]; then
    echo "    Mode: Twilio Voice (Outbound PSTN). Ensure TWILIO_ACCOUNT_SID is set."
elif [ "$NORMALIZED_MODE" = "fake" ]; then
    echo "    Mode: Fake Telephony (Hermetic test / CI)."
fi
