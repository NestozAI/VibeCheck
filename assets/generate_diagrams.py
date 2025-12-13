"""
Generate architecture diagram for VibeCheck README
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.lines as mlines

# Set up the figure with clean style
plt.style.use('default')
fig, ax = plt.subplots(1, 1, figsize=(12, 8))
ax.set_xlim(0, 12)
ax.set_ylim(0, 8)
ax.set_aspect('equal')
ax.axis('off')

# Colors - clean grayscale with accent
DARK = '#2D3436'
MEDIUM = '#636E72'
LIGHT = '#B2BEC3'
WHITE = '#FFFFFF'
ACCENT = '#0984E3'  # Blue accent for key elements

def draw_box(ax, x, y, width, height, label, sublabel=None, color=LIGHT, text_color=DARK):
    """Draw a rounded rectangle box with label"""
    box = FancyBboxPatch((x, y), width, height,
                          boxstyle="round,pad=0.05,rounding_size=0.2",
                          facecolor=color, edgecolor=DARK, linewidth=2)
    ax.add_patch(box)

    if sublabel:
        ax.text(x + width/2, y + height/2 + 0.15, label,
                ha='center', va='center', fontsize=11, fontweight='bold', color=text_color)
        ax.text(x + width/2, y + height/2 - 0.25, sublabel,
                ha='center', va='center', fontsize=9, color=MEDIUM)
    else:
        ax.text(x + width/2, y + height/2, label,
                ha='center', va='center', fontsize=11, fontweight='bold', color=text_color)

def draw_arrow(ax, start, end, label=None, color=DARK):
    """Draw an arrow between points"""
    ax.annotate('', xy=end, xytext=start,
                arrowprops=dict(arrowstyle='->', color=color, lw=2))
    if label:
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        ax.text(mid_x, mid_y + 0.2, label, ha='center', va='bottom', fontsize=9, color=MEDIUM)

# Title
ax.text(6, 7.5, 'VibeCheck Architecture', ha='center', va='center',
        fontsize=16, fontweight='bold', color=DARK)

# === SLACK SECTION ===
# Slack container
slack_box = FancyBboxPatch((0.5, 4.5), 3, 2.5,
                            boxstyle="round,pad=0.05,rounding_size=0.3",
                            facecolor='#F8F9FA', edgecolor=DARK, linewidth=2)
ax.add_patch(slack_box)
ax.text(2, 6.7, 'Slack', ha='center', va='center', fontsize=12, fontweight='bold', color=DARK)

# Slack components
draw_box(ax, 0.8, 5.5, 1.1, 0.7, 'DM', color=WHITE)
draw_box(ax, 2.1, 5.5, 1.1, 0.7, 'Channel', color=WHITE)
draw_box(ax, 1.45, 4.7, 1.1, 0.6, 'Buttons', color=WHITE)

# === YOUR SERVER SECTION ===
# Server container
server_box = FancyBboxPatch((4.5, 1), 7, 5.5,
                             boxstyle="round,pad=0.05,rounding_size=0.3",
                             facecolor='#F8F9FA', edgecolor=DARK, linewidth=2)
ax.add_patch(server_box)
ax.text(8, 6.2, 'Your Server', ha='center', va='center', fontsize=12, fontweight='bold', color=DARK)

# Main.py box
main_box = FancyBboxPatch((5, 3), 6, 2.8,
                           boxstyle="round,pad=0.05,rounding_size=0.2",
                           facecolor=WHITE, edgecolor=MEDIUM, linewidth=1.5)
ax.add_patch(main_box)
ax.text(8, 5.5, 'main.py', ha='center', va='center', fontsize=11, fontweight='bold', color=DARK)

# Components inside main.py
draw_box(ax, 5.3, 4.2, 1.7, 0.8, 'Security', 'Layer', color=LIGHT)
draw_box(ax, 7.15, 4.2, 1.7, 0.8, 'Image', 'Upload', color=LIGHT)
draw_box(ax, 9, 4.2, 1.7, 0.8, 'Runner', color=ACCENT, text_color=WHITE)
draw_box(ax, 7.15, 3.2, 1.7, 0.8, 'Session', 'Manager', color=LIGHT)

# AI CLI box
draw_box(ax, 6.5, 1.3, 3, 1, 'AI Coding CLI', '(subprocess)', color=DARK, text_color=WHITE)

# === ARROWS ===
# Slack to Server (Socket Mode)
ax.annotate('', xy=(4.5, 5.5), xytext=(3.5, 5.5),
            arrowprops=dict(arrowstyle='<->', color=ACCENT, lw=2.5))
ax.text(4, 5.85, 'Socket Mode', ha='center', va='bottom', fontsize=9, fontweight='bold', color=ACCENT)

# Runner to CLI
ax.annotate('', xy=(8, 2.3), xytext=(8, 3.2),
            arrowprops=dict(arrowstyle='->', color=DARK, lw=2))

# Security flow indicator
ax.annotate('', xy=(7.15, 4.6), xytext=(7, 4.6),
            arrowprops=dict(arrowstyle='->', color=MEDIUM, lw=1.5))

plt.tight_layout()
plt.savefig('/disk1/lecture/sotaaz/vibe-coding-bot/assets/architecture.png',
            dpi=150, bbox_inches='tight', facecolor='white', edgecolor='none')
plt.close()

print("Architecture diagram saved!")

# === SECURITY FLOW DIAGRAM ===
fig2, ax2 = plt.subplots(1, 1, figsize=(10, 6))
ax2.set_xlim(0, 10)
ax2.set_ylim(0, 6)
ax2.set_aspect('equal')
ax2.axis('off')

# Title
ax2.text(5, 5.5, 'Security Approval Flow', ha='center', va='center',
         fontsize=14, fontweight='bold', color=DARK)

# Flow boxes
draw_box(ax2, 0.5, 3.5, 2, 1, 'User', 'Request', color=WHITE)
draw_box(ax2, 3, 3.5, 2, 1, 'Path', 'Detection', color=LIGHT)
draw_box(ax2, 5.7, 4.2, 2, 0.8, 'Trusted?', color=ACCENT, text_color=WHITE)
draw_box(ax2, 5.7, 2.5, 2, 0.8, 'Approval UI', color='#FDCB6E')
draw_box(ax2, 8.2, 3.5, 1.5, 1, 'Execute', color='#00B894', text_color=WHITE)

# Arrows
ax2.annotate('', xy=(3, 4), xytext=(2.5, 4),
            arrowprops=dict(arrowstyle='->', color=DARK, lw=2))
ax2.annotate('', xy=(5.7, 4.6), xytext=(5, 4),
            arrowprops=dict(arrowstyle='->', color=DARK, lw=2))

# Yes arrow
ax2.annotate('', xy=(8.2, 4), xytext=(7.7, 4.6),
            arrowprops=dict(arrowstyle='->', color='#00B894', lw=2))
ax2.text(8.1, 4.5, 'Yes', ha='center', va='center', fontsize=9, color='#00B894', fontweight='bold')

# No arrow
ax2.annotate('', xy=(6.7, 3.3), xytext=(6.7, 4.2),
            arrowprops=dict(arrowstyle='->', color='#D63031', lw=2))
ax2.text(7.1, 3.75, 'No', ha='center', va='center', fontsize=9, color='#D63031', fontweight='bold')

# Approval to Execute
ax2.annotate('', xy=(8.2, 3.5), xytext=(7.7, 2.9),
            arrowprops=dict(arrowstyle='->', color=DARK, lw=2))
ax2.text(8.2, 3.1, 'Approve', ha='center', va='center', fontsize=8, color=MEDIUM)

plt.tight_layout()
plt.savefig('/disk1/lecture/sotaaz/vibe-coding-bot/assets/security_flow.png',
            dpi=150, bbox_inches='tight', facecolor='white', edgecolor='none')
plt.close()

print("Security flow diagram saved!")
