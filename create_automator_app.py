#!/usr/bin/env python3
"""
Create a macOS app with Automator that runs the .command file.
This gives us the icon + reliability of the .command file.
"""

import os
import shutil
from pathlib import Path
from subprocess import run

# Create app bundle structure
app_dir = Path("/Applications/Wealth Management.app")
contents_dir = app_dir / "Contents"
macos_dir = contents_dir / "MacOS"
resources_dir = contents_dir / "Resources"

# Clean if exists
if app_dir.exists():
    shutil.rmtree(app_dir)

# Create directories
macos_dir.mkdir(parents=True, exist_ok=True)
resources_dir.mkdir(parents=True, exist_ok=True)

# Create the launcher script
launcher = macos_dir / "Wealth Management"
launcher.write_text("""#!/bin/bash
open /Applications/Wealth\\ Management.command
""")
launcher.chmod(0o755)

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
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
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

# Copy icon if it exists
icon_path = Path("wealth_management_icon.icns")
if icon_path.exists():
    shutil.copy(icon_path, resources_dir / "AppIcon.icns")
    print(f"✅ Icon installed")
else:
    print(f"⚠️ Icon not found, app will have default icon")

print(f"✅ App created: {app_dir}")
