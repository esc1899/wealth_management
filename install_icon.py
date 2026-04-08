#!/usr/bin/env python3
"""
Convert PNG icon to macOS .icns format and install in the app bundle.
"""

from PIL import Image
from pathlib import Path
import subprocess
import os

icon_png = Path("wealth_management_icon.png")
icon_icns = Path("wealth_management_icon.icns")
app_dir = Path.home() / "Applications" / "Wealth Management.app"
resources_dir = app_dir / "Contents" / "Resources"

if not icon_png.exists():
    print(f"❌ Icon file not found: {icon_png}")
    exit(1)

# macOS .icns creation requires specific sizes
# We'll use sips (built-in macOS tool) to convert
print("Converting PNG to ICNS...")

# Create iconset directory
iconset_dir = Path("wealth_management.iconset")
if iconset_dir.exists():
    import shutil
    shutil.rmtree(iconset_dir)
iconset_dir.mkdir()

# Generate all required sizes for macOS
sizes = [16, 32, 64, 128, 256, 512]
img = Image.open(icon_png)

for size in sizes:
    # Create @1x version
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    resized.save(iconset_dir / f"icon_{size}x{size}.png")

    # Create @2x version
    resized_2x = img.resize((size*2, size*2), Image.Resampling.LANCZOS)
    resized_2x.save(iconset_dir / f"icon_{size}x{size}@2x.png")

print(f"Created iconset: {iconset_dir}")

# Convert iconset to .icns using iconutil (built-in)
result = subprocess.run(
    ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icon_icns)],
    capture_output=True,
    text=True
)

if result.returncode != 0:
    print(f"❌ iconutil failed: {result.stderr}")
    exit(1)

print(f"✅ Created {icon_icns}")

# Copy to app resources
resources_dir.mkdir(parents=True, exist_ok=True)
import shutil
shutil.copy(icon_icns, resources_dir / "AppIcon.icns")
print(f"✅ Installed to {resources_dir / 'AppIcon.icns'}")

# Update Info.plist to reference the icon
plist_path = app_dir / "Contents" / "Info.plist"
plist_content = plist_path.read_text()

# Add icon reference if not present
if "CFBundleIconFile" not in plist_content:
    # Insert before closing </dict>
    plist_content = plist_content.replace(
        "</dict>",
        """    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
</dict>"""
    )
    plist_path.write_text(plist_content)
    print("✅ Updated Info.plist with icon reference")

# Clean up
import shutil
shutil.rmtree(iconset_dir)

print(f"\n✅ Icon installed successfully!")
print(f"The app icon will appear after you restart the app or refresh Finder.")
