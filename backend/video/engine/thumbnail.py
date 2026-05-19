import random
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

from video.engine.utils import sanitize_filename


class ThumbnailGenerator:
    GRADIENTS = [
        ((255, 107, 107), (255, 142, 83)),
        ((78, 205, 196), (68, 160, 141)),
        ((199, 121, 208), (75, 192, 200)),
        ((240, 147, 251), (245, 87, 108)),
        ((67, 233, 123), (56, 249, 215)),
        ((48, 207, 208), (51, 8, 103)),
        ((255, 154, 158), (250, 208, 196)),
        ((102, 126, 234), (118, 75, 162)),
    ]

    def __init__(self, width: int = 1280, height: int = 720):
        self.width = width
        self.height = height

    def _get_font(self, size: int) -> ImageFont.FreeTypeFont:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
        for path in font_paths:
            try:
                return ImageFont.truetype(path, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    def _create_gradient(self, color1: Tuple[int, int, int], color2: Tuple[int, int, int]) -> Image.Image:
        base = Image.new("RGB", (self.width, self.height), color1)
        draw = ImageDraw.Draw(base)

        for y in range(self.height):
            r = int(color1[0] + (color2[0] - color1[0]) * y / self.height)
            g = int(color1[1] + (color2[1] - color1[1]) * y / self.height)
            b = int(color1[2] + (color2[2] - color1[2]) * y / self.height)
            draw.line([(0, y), (self.width, y)], fill=(r, g, b))

        return base

    def _add_text_shadow(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        x: int,
        y: int,
        shadow_color: Tuple[int, int, int] = (0, 0, 0),
        offset: int = 3,
    ) -> None:
        for dx in range(-offset, offset + 1):
            for dy in range(-offset, offset + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, font=font, fill=shadow_color)

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        words = text.split()
        lines = []
        current = []

        for word in words:
            test = " ".join(current + [word])
            bbox = font.getbbox(test)
            if bbox and (bbox[2] - bbox[0]) > max_width and current:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)

        if current:
            lines.append(" ".join(current))

        return lines

    def generate(
        self,
        title: str,
        subreddit: str,
        output_path: Path,
        score: Optional[int] = None,
    ) -> Path:
        color1, color2 = random.choice(self.GRADIENTS)
        img = self._create_gradient(color1, color2)

        overlay = Image.new("RGBA", (self.width, self.height), (255, 255, 255, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        for _ in range(5):
            x = random.randint(0, self.width)
            y = random.randint(0, self.height)
            r = random.randint(50, 200)
            overlay_draw.ellipse(
                [x - r, y - r, x + r, y + r],
                fill=(255, 255, 255, 15),
            )

        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        img = img.filter(ImageFilter.GaussianBlur(radius=0.5))

        draw = ImageDraw.Draw(img)

        badge_font = self._get_font(28)
        badge_text = f"r/{subreddit}"
        bbox = badge_font.getbbox(badge_text)
        badge_w = (bbox[2] - bbox[0]) + 40 if bbox else 200
        badge_h = (bbox[3] - bbox[1]) + 20 if bbox else 50

        badge_x = self.width - badge_w - 30
        badge_y = 30
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
            radius=20,
            fill=(255, 255, 255),
            outline=(255, 255, 255),
            width=2,
        )
        draw.text(
            (badge_x + 20, badge_y + 8),
            badge_text,
            font=badge_font,
            fill=(0, 0, 0),
        )

        if score:
            score_font = self._get_font(24)
            score_text = f"↑ {score:,}"
            score_bbox = score_font.getbbox(score_text)
            score_w = (score_bbox[2] - score_bbox[0]) + 30 if score_bbox else 150
            score_h = (score_bbox[3] - score_bbox[1]) + 14 if score_bbox else 40
            score_x = 30
            score_y = 30

            draw.rounded_rectangle(
                [score_x, score_y, score_x + score_w, score_y + score_h],
                radius=15,
                fill=(255, 69, 0),
                outline=(255, 255, 255),
                width=2,
            )
            draw.text(
                (score_x + 15, score_y + 5),
                score_text,
                font=score_font,
                fill=(255, 255, 255),
            )

        title_font_large = self._get_font(72)
        title_font_medium = self._get_font(56)
        title_font_small = self._get_font(42)

        max_width = self.width - 100
        wrapped = self._wrap_text(title, title_font_large, max_width)

        font = title_font_large
        if len(wrapped) > 3:
            wrapped = self._wrap_text(title, title_font_medium, max_width)
            font = title_font_medium
        if len(wrapped) > 4:
            wrapped = self._wrap_text(title, title_font_small, max_width)
            font = title_font_small

        if len(wrapped) > 5:
            wrapped = wrapped[:4]
            wrapped[-1] = wrapped[-1][:40] + "..."

        line_height = font.size + 15
        total_height = len(wrapped) * line_height
        start_y = (self.height - total_height) // 2 - 20

        for i, line in enumerate(wrapped):
            bbox = font.getbbox(line)
            text_w = (bbox[2] - bbox[0]) if bbox else 0
            x = (self.width - text_w) // 2
            y = start_y + i * line_height

            self._add_text_shadow(draw, line, font, x, y, shadow_color=(0, 0, 0), offset=4)
            draw.text((x, y), line, font=font, fill=(255, 255, 255))

        watermark_font = self._get_font(20)
        watermark = "Reddit Story"
        wbbox = watermark_font.getbbox(watermark)
        wx = (self.width - ((wbbox[2] - wbbox[0]) if wbbox else 100)) // 2
        wy = self.height - 60
        draw.text((wx, wy), watermark, font=watermark_font, fill=(255, 255, 255))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "JPEG", quality=90, optimize=True)

        return output_path
