#!/usr/bin/env python3
"""
Restart Streamlit App — clears cache and restarts fresh
Simply run this script to refresh everything
"""

import subprocess
import shutil
import os
import sys
from pathlib import Path

print("🧹 Clearing Streamlit cache...")
cache_dirs = [
    Path.home() / ".streamlit" / "cache",
    Path.home() / ".cache" / "streamlit",
]

for cache_dir in cache_dirs:
    if cache_dir.exists():
        try:
            shutil.rmtree(cache_dir)
            print(f"  ✅ {cache_dir}")
        except Exception as e:
            print(f"  ⚠️  {cache_dir}: {e}")

print("\n🚀 Starting Streamlit app...\n")

# Start streamlit
try:
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "app.py"],
        cwd="/Users/erik/Projects/wealth_management",
    )
except KeyboardInterrupt:
    print("\n\n👋 App stopped.")
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
