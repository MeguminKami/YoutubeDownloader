"""Logo image helpers for consistent rounded/soft rendering."""
import os
from typing import Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps


def load_soft_logo_ctk_image(
    logo_path: str,
    size: Tuple[int, int],
    corner_radius: Optional[int] = None,
    feather_px: Optional[int] = None,
):
    """Return a CTkImage with rounded corners and feathered alpha edges."""
    if not logo_path or not os.path.exists(logo_path):
        return None

    width, height = size
    min_side = min(width, height)
    radius = max(2, int(min_side * 0.24)) if corner_radius is None else max(2, int(corner_radius))
    feather = max(0, int(min_side * 0.10)) if feather_px is None else max(0, int(feather_px))

    try:
        with Image.open(logo_path) as source:
            rgba = ImageOps.fit(source.convert("RGBA"), size, method=Image.Resampling.LANCZOS)

        round_mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(round_mask)
        draw.rounded_rectangle((0, 0, width, height), radius=radius, fill=255)

        if feather > 0:
            round_mask = round_mask.filter(ImageFilter.GaussianBlur(feather / 2.0))

        alpha = rgba.getchannel("A")
        softened_alpha = ImageChops.multiply(alpha, round_mask)
        rgba.putalpha(softened_alpha)

        return ctk.CTkImage(light_image=rgba.copy(), dark_image=rgba.copy(), size=size)
    except Exception:
        return None

