#!/usr/bin/env python3
"""
Create a macOS .app bundle for Wealth Management.
Run once: python3 create_app.py
The app will appear in ~/Applications/Wealth Management.app
"""

import os
import shutil
from pathlib import Path

# Paths
project_dir = Path(__file__).parent
app_dir = Path.home() / "Applications" / "Wealth Management.app"
contents_dir = app_dir / "Contents"
macos_dir = contents_dir / "MacOS"
resources_dir = contents_dir / "Resources"

# Clean if exists
if app_dir.exists():
    shutil.rmtree(app_dir)
    print(f"Removed existing {app_dir}")

# Create directories
macos_dir.mkdir(parents=True, exist_ok=True)
resources_dir.mkdir(parents=True, exist_ok=True)

# Create executable script
launcher = macos_dir / "Wealth Management"
launcher.write_text(f"""#!/bin/bash
cd "{project_dir}"
source .venv/bin/activate
streamlit run app.py
""")
launcher.chmod(0o755)
print(f"Created launcher: {launcher}")

# Create Info.plist
plist = contents_dir / "Info.plist"
plist.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>Wealth Management</string>
    <key>CFBundleIdentifier</key>
    <string>com.local.wealth-management</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Wealth Management</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
</dict>
</plist>
""")
print(f"Created Info.plist")

print(f"\n✅ App created: {app_dir}")
print(f"You can now:")
print(f"  - Open it from Applications folder")
print(f"  - Add it to Dock by dragging it there")
print(f"  - Right-click → Add to Dock for quick access")
