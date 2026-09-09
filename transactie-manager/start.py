#!/usr/bin/env python3
"""Start de toepassing met waitress. Werkt op Windows, Linux en macOS."""

from __future__ import annotations

import sys
import webbrowser

from app import create_app
from app.config import APP_NAME, HOST, PORT, VERSION


def main() -> int:
    toepassing = create_app()

    adres = f"http://127.0.0.1:{PORT}/"
    print(f"{APP_NAME} {VERSION}")
    print(f"Open de toepassing op {adres}")
    print("Stoppen met Ctrl+C.\n")

    if "--geen-browser" not in sys.argv:
        try:
            webbrowser.open(adres)
        except Exception:  # noqa: BLE001
            pass

    try:
        from waitress import serve
        serve(toepassing, host=HOST, port=PORT, threads=8)
    except ImportError:
        print("waitress is niet geïnstalleerd; de ingebouwde server wordt gebruikt.")
        toepassing.run(host=HOST, port=PORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
