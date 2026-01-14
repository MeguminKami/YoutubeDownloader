"""Reusable UI widgets"""
import customtkinter as ctk

def create_tooltip(widget, text, theme_colors):
    """Create hover tooltip for widget"""
    tooltip = None

    def on_enter(event):
        nonlocal tooltip
        tooltip = ctk.CTkToplevel()
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")

        label = ctk.CTkLabel(
            tooltip, text=text, fg_color=theme_colors.surface,
            corner_radius=8, padx=10, pady=5, text_color=theme_colors.text_primary
        )
        label.pack()

    def on_leave(event):
        nonlocal tooltip
        if tooltip:
            tooltip.destroy()
            tooltip = None

    widget.bind('<Enter>', on_enter)
    widget.bind('<Leave>', on_leave)
