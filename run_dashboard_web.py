"""
Phi Web-Dashboard starten.

Nutzung:
    python run_dashboard_web.py              # Standard (Port 8080)
    python run_dashboard_web.py --port 3000  # Anderer Port
    python run_dashboard_web.py --open       # Browser automatisch oeffnen
"""

import argparse
import sys
import webbrowser
from pathlib import Path

# Engine-Pfad sicherstellen
sys.path.insert(0, str(Path(__file__).parent))


def main():
    parser = argparse.ArgumentParser(description="Phi Web-Dashboard")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--open", action="store_true", help="Browser automatisch oeffnen")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("\n  Fehlende Abhaengigkeit: uvicorn")
        print("  Installation: pip install uvicorn fastapi websockets\n")
        sys.exit(1)

    url = f"http://{args.host}:{args.port}"
    print(f"\n  Phi Dashboard startet auf {url}")
    print("  Ctrl+C zum Beenden\n")

    if args.open:
        webbrowser.open(url)

    uvicorn.run(
        "web.app:app",
        host=args.host,
        port=args.port,
        log_level="warning",
        reload=False,
    )


if __name__ == "__main__":
    main()
