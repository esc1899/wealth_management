#!/usr/bin/env python3
"""
Generate a macOS app icon for Wealth Management.
Creates a 512x512 icon with a wealth/portfolio theme.
"""

from PIL import Image, ImageDraw
import os

# Create a 512x512 image with rounded corners effect
size = 512
icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(icon)

# Background: gradient-like solid color (teal/blue)
bg_color = (20, 130, 150)  # Teal
draw.rectangle([(0, 0), (size, size)], fill=bg_color)

# Draw a simple bar chart (portfolio rebalancing theme)
bar_width = 80
bar_height = 200
spacing = 30
start_x = 120
start_y = 280

# Bar 1 (Aktien - green)
draw.rectangle(
    [(start_x, start_y - bar_height), (start_x + bar_width, start_y)],
    fill=(76, 200, 100),
)

# Bar 2 (Renten - yellow)
draw.rectangle(
    [(start_x + bar_width + spacing, start_y - bar_height * 0.7),
     (start_x + 2*bar_width + spacing, start_y)],
    fill=(255, 193, 7),
)

# Bar 3 (Rohstoffe - orange)
draw.rectangle(
    [(start_x + 2*(bar_width + spacing), start_y - bar_height * 0.5),
     (start_x + 3*bar_width + 2*spacing, start_y)],
    fill=(255, 152, 0),
)

# Draw a money symbol (€) at the top
draw.text(
    (size // 2 - 40, 80),
    "💰",
    font=None,  # Default font
)

# Save as PNG
icon_path = "wealth_management_icon.png"
icon.save(icon_path, "PNG")
print(f"✅ Icon created: {icon_path}")
print(f"Size: {size}x{size} pixels")
