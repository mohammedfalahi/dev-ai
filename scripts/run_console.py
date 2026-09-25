import subprocess
import sys
import time
from pathlib import Path


def main():
    root_dir = Path(__file__).parent.parent

    print("Starting labs/broken-shop on port 8081...")
    broken_shop_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "labs.broken_shop.app:app", "--port", "8081"],
        cwd=root_dir,
    )

    # Give broken shop a second to start
    time.sleep(1)

    print("Starting apps/console on port 8080...")
    console_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "apps.console.app:app",
            "--port",
            "8080",
            "--reload",
        ],
        cwd=root_dir,
    )

    try:
        console_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down servers...")
        console_proc.terminate()
        broken_shop_proc.terminate()
        console_proc.wait()
        broken_shop_proc.wait()
        print("Shutdown complete.")


if __name__ == "__main__":
    main()
