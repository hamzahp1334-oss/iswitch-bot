"""
iSwitch Store Telegram Bot - Main Application Entrypoint
Suitable for direct execution, local hosting, Docker, and Render deployment.
"""

import asyncio
import sys
from pathlib import Path

# Ensure root directory is on Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from run import run_bots

if __name__ == "__main__":
    try:
        asyncio.run(run_bots())
    except KeyboardInterrupt:
        print("\nExiting iSwitch Commerce System.")
