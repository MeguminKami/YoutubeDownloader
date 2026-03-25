"""Programmatic icon and brand asset generation for the UI."""
from __future__ import annotations

import math
import os
import tempfile
from typing import Dict, Optional, Tuple, Union

import customtkinter as ctk
from PIL import Image, ImageColor, ImageDraw, ImageOps, ImageTk

from core.deps import find_bundled_resource


ColorLike = Union[str, Tuple[int, int, int], Tuple[int, int, int, int]]


def _rgb(color: ColorLike) -> Tuple[int, int, int]:
    if isinstance(color, tuple):
        return tuple(color[:3])
    return ImageColor.getrgb(color)


def _rgba(color: ColorLike, alpha: int = 255) -> Tuple[int, int, int, int]:
    red, green, blue = _rgb(color)
    return red, green, blue, max(0, min(255, int(alpha)))


def _mix(a: ColorLike, b: ColorLike, ratio: float) -> Tuple[int, int, int]:
    ratio = max(0.0, min(1.0, float(ratio)))
    ar, ag, ab = _rgb(a)
    br, bg, bb = _rgb(b)
    return (
        int(ar + (br - ar) * ratio),
        int(ag + (bg - ag) * ratio),
        int(ab + (bb - ab) * ratio),
    )


class VisualAssets:
    """Creates CTkImage assets on demand and caches them per theme."""

    def __init__(self, colors):
        self.colors = colors
        self._logo_path = (
            find_bundled_resource("ui", "logo.png")
            or os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        )
        self._render_scale = 2
        self._image_cache: Dict[Tuple, ctk.CTkImage] = {}

    def brand_mark(self, size: int = 36) -> ctk.CTkImage:
        render_size = size * self._render_scale
        return self._ctk_image(
            ("brand", size, self._render_scale, self._logo_signature()),
            lambda: self._render_brand_mark(render_size),
            display_size=(size, size),
        )

    def brand_photoimage(self, size: int = 64):
        return ImageTk.PhotoImage(self._render_brand_mark(size))

    def save_brand_ico(self) -> Optional[str]:
        try:
            icon_path = os.path.join(tempfile.gettempdir(), "ytgrab_brand_icon.ico")
            brand = self._render_brand_mark(256)
            brand.save(icon_path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128)])
            return icon_path
        except Exception:
            return None

    def icon(self, name: str, size: int = 18, color: Optional[ColorLike] = None) -> ctk.CTkImage:
        resolved_color = color or self.colors.text_primary
        render_size = size * self._render_scale
        key = ("icon", name, size, str(resolved_color), self._render_scale)
        return self._ctk_image(key, lambda: self._render_icon(name, render_size, resolved_color), display_size=(size, size))

    def media_tile(self, size: Tuple[int, int], item_type: str = "video") -> ctk.CTkImage:
        render_size = self._scaled_dimensions(size)
        key = ("tile", size, item_type, self.colors.surface, self.colors.primary, self._render_scale)
        return self._ctk_image(key, lambda: self._render_media_tile(render_size, item_type), display_size=size)

    def empty_state_tile(self, size: Tuple[int, int], icon_name: str) -> ctk.CTkImage:
        render_size = self._scaled_dimensions(size)
        key = ("empty", size, icon_name, self.colors.surface_alt, self.colors.text_muted, self._render_scale)
        return self._ctk_image(key, lambda: self._render_empty_tile(render_size, icon_name), display_size=size)

    def local_media_image(self, image_path: str, size: Tuple[int, int], corner_radius: int = 14) -> Optional[ctk.CTkImage]:
        if not image_path or not os.path.exists(image_path):
            return None

        try:
            image_stat = os.path.getmtime(image_path)
        except Exception:
            image_stat = 0

        render_size = self._scaled_dimensions(size)
        render_radius = corner_radius * self._render_scale
        key = ("local-media", image_path, size, corner_radius, image_stat, self._render_scale)
        return self._ctk_image(
            key,
            lambda: self._render_local_media_image(image_path, render_size, render_radius),
            display_size=size,
        )

    def _scaled_dimensions(self, size: Tuple[int, int]) -> Tuple[int, int]:
        width, height = size
        return max(1, int(width * self._render_scale)), max(1, int(height * self._render_scale))

    def _ctk_image(self, key: Tuple, renderer, display_size: Optional[Tuple[int, int]] = None) -> ctk.CTkImage:
        if key not in self._image_cache:
            pil_image = renderer()
            target_size = display_size or pil_image.size
            self._image_cache[key] = ctk.CTkImage(
                light_image=pil_image.copy(),
                dark_image=pil_image.copy(),
                size=target_size,
            )
        return self._image_cache[key]

    def _logo_signature(self) -> float:
        try:
            return os.path.getmtime(self._logo_path)
        except Exception:
            return 0.0

    def _load_logo_source(self) -> Optional[Image.Image]:
        if not os.path.exists(self._logo_path):
            return None
        try:
            with Image.open(self._logo_path) as source:
                return source.convert("RGBA")
        except Exception:
            return None

    def _render_logo_canvas(self, size: Tuple[int, int], padding_ratio: float = 0.08) -> Optional[Image.Image]:
        source = self._load_logo_source()
        if source is None:
            return None

        width, height = size
        padding = max(0, int(min(width, height) * padding_ratio))
        inner_width = max(1, width - padding * 2)
        inner_height = max(1, height - padding * 2)

        contained = ImageOps.contain(source, (inner_width, inner_height), method=Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        paste_x = (width - contained.size[0]) // 2
        paste_y = (height - contained.size[1]) // 2
        canvas.alpha_composite(contained, (paste_x, paste_y))
        return canvas

    def _render_brand_mark(self, size: int) -> Image.Image:
        logo_canvas = self._render_logo_canvas((size, size), padding_ratio=0.0)
        if logo_canvas is not None:
            return logo_canvas

        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        radius = max(8, size // 4)
        draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=_rgba(self.colors.primary))

        inset = size * 0.22
        triangle = [
            (inset, size * 0.26),
            (inset, size * 0.74),
            (size * 0.74, size * 0.50),
        ]
        draw.polygon(triangle, fill=(255, 255, 255, 255))
        return canvas

    def _render_media_tile(self, size: Tuple[int, int], item_type: str) -> Image.Image:
        width, height = size
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        base_fill = _mix(self.colors.surface_alt, self.colors.primary, 0.08 if item_type == "video" else 0.04)
        edge_fill = _mix(self.colors.border, self.colors.primary, 0.22 if item_type == "video" else 0.10)
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=14, fill=_rgba(base_fill), outline=_rgba(edge_fill))

        highlight = _mix(self.colors.primary, "#ffffff", 0.35 if item_type == "video" else 0.12)
        draw.arc((-width * 0.25, -height * 0.70, width * 1.25, height * 1.60), start=12, end=170, fill=_rgba(highlight, 90), width=max(2, height // 10))
        draw.line((0, height - 8, width, height - 18), fill=_rgba(self.colors.primary, 70), width=max(2, height // 12))

        brand_size = max(22, int(height * 0.66))
        logo = self._render_logo_canvas((brand_size, brand_size), padding_ratio=0.0)
        if logo is not None:
            brand_x = int(width * 0.5 - brand_size * 0.5)
            brand_y = int(height * 0.5 - brand_size * 0.5)
            canvas.alpha_composite(logo, (brand_x, brand_y))
        else:
            brand = self._render_brand_mark(brand_size)
            brand_x = int(width * 0.5 - brand_size * 0.5)
            brand_y = int(height * 0.5 - brand_size * 0.5)
            canvas.alpha_composite(brand, (brand_x, brand_y))

        if item_type == "audio":
            note = self._render_icon("music", max(14, int(height * 0.34)), "#ffffff")
            badge_size = note.size[0] + 10
            badge = Image.new("RGBA", (badge_size, badge_size), (0, 0, 0, 0))
            badge_draw = ImageDraw.Draw(badge)
            badge_draw.rounded_rectangle((0, 0, badge_size - 1, badge_size - 1), radius=badge_size // 3, fill=_rgba(self.colors.primary))
            badge.alpha_composite(note, ((badge_size - note.size[0]) // 2, (badge_size - note.size[1]) // 2))
            canvas.alpha_composite(badge, (width - badge_size - 8, 8))

        return canvas

    def _render_empty_tile(self, size: Tuple[int, int], icon_name: str) -> Image.Image:
        width, height = size
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=min(width, height) // 4, fill=_rgba(self.colors.surface_alt))
        icon = self._render_icon(icon_name, min(width, height) // 2, self.colors.text_muted)
        canvas.alpha_composite(icon, ((width - icon.size[0]) // 2, (height - icon.size[1]) // 2))
        return canvas

    def _render_local_media_image(self, image_path: str, size: Tuple[int, int], corner_radius: int) -> Image.Image:
        width, height = size
        with Image.open(image_path) as source:
            rgba = ImageOps.fit(source.convert("RGBA"), size, method=Image.Resampling.LANCZOS)

        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=max(2, int(corner_radius)), fill=255)
        rgba.putalpha(mask)
        return rgba

    def _render_icon(self, name: str, size: int, color: ColorLike) -> Image.Image:
        name = name.lower()
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        stroke = max(2, size // 8)
        inset = stroke / 2 + 1
        fg = _rgba(color)

        if name in {"queue", "list"}:
            left = size * 0.18
            for idx, top in enumerate((0.23, 0.48, 0.73)):
                y = size * top
                draw.rounded_rectangle((left, y - stroke / 2, size * 0.86, y + stroke / 2), radius=stroke, fill=fg)
                dot = size * (0.11 + idx * 0.005)
                draw.ellipse((dot - stroke, y - stroke, dot + stroke, y + stroke), fill=fg)
        elif name == "history":
            draw.arc((inset, inset, size - inset, size - inset), start=32, end=320, fill=fg, width=stroke)
            tip = (size * 0.68, size * 0.12)
            draw.line((tip[0], tip[1], size * 0.90, size * 0.14), fill=fg, width=stroke)
            draw.line((tip[0], tip[1], size * 0.82, size * 0.28), fill=fg, width=stroke)
        elif name == "download":
            draw.line((size * 0.50, size * 0.18, size * 0.50, size * 0.62), fill=fg, width=stroke)
            draw.line((size * 0.34, size * 0.48, size * 0.50, size * 0.66), fill=fg, width=stroke)
            draw.line((size * 0.66, size * 0.48, size * 0.50, size * 0.66), fill=fg, width=stroke)
            draw.rounded_rectangle((size * 0.18, size * 0.74, size * 0.82, size * 0.84), radius=stroke, outline=fg, width=stroke)
        elif name == "paste":
            draw.rounded_rectangle((size * 0.22, size * 0.20, size * 0.78, size * 0.86), radius=stroke + 1, outline=fg, width=stroke)
            draw.rounded_rectangle((size * 0.35, size * 0.10, size * 0.65, size * 0.28), radius=stroke, outline=fg, width=stroke)
            draw.line((size * 0.34, size * 0.46, size * 0.66, size * 0.46), fill=fg, width=stroke)
            draw.line((size * 0.34, size * 0.62, size * 0.60, size * 0.62), fill=fg, width=stroke)
        elif name == "moon":
            draw.ellipse((size * 0.18, size * 0.16, size * 0.84, size * 0.84), fill=fg)
            cut = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            cut_draw = ImageDraw.Draw(cut)
            cut_draw.ellipse((size * 0.38, size * 0.08, size * 0.92, size * 0.80), fill=(0, 0, 0, 255))
            canvas = Image.alpha_composite(canvas, Image.eval(cut, lambda _: 0))
            # Rebuild moon using mask subtraction.
            moon = Image.new("L", (size, size), 0)
            moon_draw = ImageDraw.Draw(moon)
            moon_draw.ellipse((size * 0.18, size * 0.16, size * 0.84, size * 0.84), fill=255)
            moon_draw.ellipse((size * 0.38, size * 0.08, size * 0.92, size * 0.80), fill=0)
            final_canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            final_canvas.paste(Image.new("RGBA", (size, size), fg), mask=moon)
            canvas = final_canvas
        elif name == "sun":
            draw.ellipse((size * 0.28, size * 0.28, size * 0.72, size * 0.72), outline=fg, width=stroke)
            for angle in range(0, 360, 45):
                inner = size * 0.18
                outer = size * 0.34
                x1 = size / 2 + math.cos(math.radians(angle)) * inner
                y1 = size / 2 + math.sin(math.radians(angle)) * inner
                x2 = size / 2 + math.cos(math.radians(angle)) * outer
                y2 = size / 2 + math.sin(math.radians(angle)) * outer
                draw.line((x1, y1, x2, y2), fill=fg, width=stroke)
        elif name == "video":
            draw.rounded_rectangle((size * 0.12, size * 0.22, size * 0.88, size * 0.78), radius=stroke + 1, outline=fg, width=stroke)
            draw.polygon(
                [(size * 0.42, size * 0.37), (size * 0.42, size * 0.63), (size * 0.66, size * 0.50)],
                fill=fg,
            )
        elif name == "music":
            draw.line((size * 0.62, size * 0.20, size * 0.62, size * 0.64), fill=fg, width=stroke)
            draw.line((size * 0.36, size * 0.28, size * 0.62, size * 0.20), fill=fg, width=stroke)
            draw.ellipse((size * 0.18, size * 0.56, size * 0.44, size * 0.82), outline=fg, width=stroke)
            draw.ellipse((size * 0.48, size * 0.50, size * 0.74, size * 0.76), outline=fg, width=stroke)
        elif name == "check":
            draw.line((size * 0.22, size * 0.56, size * 0.42, size * 0.74), fill=fg, width=stroke)
            draw.line((size * 0.42, size * 0.74, size * 0.78, size * 0.28), fill=fg, width=stroke)
        elif name == "check_circle":
            draw.ellipse((inset, inset, size - inset, size - inset), outline=fg, width=stroke)
            draw.line((size * 0.24, size * 0.54, size * 0.43, size * 0.71), fill=fg, width=stroke)
            draw.line((size * 0.43, size * 0.71, size * 0.74, size * 0.33), fill=fg, width=stroke)
        elif name in {"alert", "alert_circle"}:
            draw.ellipse((inset, inset, size - inset, size - inset), outline=fg, width=stroke)
            draw.line((size * 0.50, size * 0.24, size * 0.50, size * 0.56), fill=fg, width=stroke)
            draw.ellipse((size * 0.45, size * 0.69, size * 0.55, size * 0.79), fill=fg)
        elif name in {"close", "x"}:
            draw.line((size * 0.24, size * 0.24, size * 0.76, size * 0.76), fill=fg, width=stroke)
            draw.line((size * 0.76, size * 0.24, size * 0.24, size * 0.76), fill=fg, width=stroke)
        elif name == "trash":
            draw.rounded_rectangle((size * 0.28, size * 0.30, size * 0.72, size * 0.82), radius=stroke, outline=fg, width=stroke)
            draw.line((size * 0.22, size * 0.26, size * 0.78, size * 0.26), fill=fg, width=stroke)
            draw.line((size * 0.42, size * 0.18, size * 0.58, size * 0.18), fill=fg, width=stroke)
            draw.line((size * 0.40, size * 0.42, size * 0.40, size * 0.68), fill=fg, width=max(1, stroke - 1))
            draw.line((size * 0.50, size * 0.42, size * 0.50, size * 0.68), fill=fg, width=max(1, stroke - 1))
            draw.line((size * 0.60, size * 0.42, size * 0.60, size * 0.68), fill=fg, width=max(1, stroke - 1))
        elif name in {"external", "link"}:
            draw.rounded_rectangle((size * 0.18, size * 0.28, size * 0.70, size * 0.80), radius=stroke, outline=fg, width=stroke)
            draw.line((size * 0.46, size * 0.22, size * 0.82, size * 0.22), fill=fg, width=stroke)
            draw.line((size * 0.82, size * 0.22, size * 0.82, size * 0.58), fill=fg, width=stroke)
            draw.line((size * 0.42, size * 0.62, size * 0.82, size * 0.22), fill=fg, width=stroke)
        elif name == "lock":
            draw.rounded_rectangle((size * 0.24, size * 0.44, size * 0.76, size * 0.82), radius=stroke + 1, outline=fg, width=stroke)
            draw.arc((size * 0.28, size * 0.16, size * 0.72, size * 0.58), start=195, end=-15, fill=fg, width=stroke)
        elif name == "cookie":
            draw.ellipse((size * 0.12, size * 0.12, size * 0.88, size * 0.88), outline=fg, width=stroke)
            draw.ellipse((size * 0.66, size * 0.24, size * 0.94, size * 0.52), fill=(0, 0, 0, 0), outline=(0, 0, 0, 0))
            draw.pieslice((size * 0.64, size * 0.18, size * 1.02, size * 0.56), start=300, end=70, fill=(0, 0, 0, 0))
            bite_mask = Image.new("L", (size, size), 0)
            bite_draw = ImageDraw.Draw(bite_mask)
            bite_draw.ellipse((size * 0.64, size * 0.16, size * 1.02, size * 0.54), fill=255)
            cookie_mask = Image.new("L", (size, size), 0)
            cookie_draw = ImageDraw.Draw(cookie_mask)
            cookie_draw.ellipse((size * 0.12, size * 0.12, size * 0.88, size * 0.88), fill=255)
            cookie_draw.bitmap((0, 0), bite_mask, fill=0)
            filled = Image.new("RGBA", (size, size), fg)
            masked = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            masked.paste(filled, mask=cookie_mask)
            canvas = masked
            draw = ImageDraw.Draw(canvas)
            for cx, cy in ((0.34, 0.32), (0.53, 0.45), (0.37, 0.60), (0.59, 0.67)):
                draw.ellipse((size * cx - 2, size * cy - 2, size * cx + 2, size * cy + 2), fill=_rgba(self.colors.surface))
        elif name == "folder":
            draw.rounded_rectangle((size * 0.12, size * 0.32, size * 0.88, size * 0.82), radius=stroke, outline=fg, width=stroke)
            draw.polygon(
                [(size * 0.14, size * 0.40), (size * 0.34, size * 0.40), (size * 0.42, size * 0.25), (size * 0.86, size * 0.25), (size * 0.86, size * 0.40)],
                outline=fg,
                fill=(0, 0, 0, 0),
            )
            draw.line((size * 0.14, size * 0.40, size * 0.34, size * 0.40, size * 0.42, size * 0.25, size * 0.86, size * 0.25), fill=fg, width=stroke)
        else:
            draw.line((size * 0.24, size * 0.24, size * 0.76, size * 0.76), fill=fg, width=stroke)
            draw.line((size * 0.76, size * 0.24, size * 0.24, size * 0.76), fill=fg, width=stroke)

        return canvas
