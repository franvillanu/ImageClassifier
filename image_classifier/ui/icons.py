"""Icon factory for SVG-based icons."""
from PyQt6.QtCore import Qt, QByteArray
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer


class IconFactory:
    _svg_strings = {
        "folder": """
            <svg width="48" height="48" viewBox="0 0 48 48"
                 preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
              <path d="M8 16C8 12.6863 10.6863 10 14 10H22.7071C23.4278 10 24.1135 10.3161
                       24.5858 10.8579L26.5 13H38C41.3137 13 44 15.6863 44 19V34C44 37.3137
                       41.3137 40 38 40H14C10.6863 40 8 37.3137 8 34V16Z"
                    fill="none" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M8 16C8 12.6863 10.6863 10 14 10H22.7071C23.4278 10 24.1135 10.3161
                       24.5858 10.8579L26.5 13H38C41.3137 13 44 15.6863 44 19V34C44 37.3137
                       41.3137 40 38 40H14C10.6863 40 8 37.3137 8 34V16Z"
                    fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        """,
        "export": """
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M6 14C6 10.6863 8.68629 8 12 8H20.7071C21.4278 8 22.1135 8.31607
                       22.5858 8.85786L24.5 11H36C39.3137 11 42 13.6863 42 17V34C42 37.3137
                       39.3137 40 36 40H12C8.68629 40 6 37.3137 6 34V14Z"
                    fill="none" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M6 14C6 10.6863 8.68629 8 12 8H20.7071C21.4278 8 22.1135 8.31607
                       22.5858 8.85786L24.5 11H36C39.3137 11 42 13.6863 42 17V34C42 37.3137
                       39.3137 40 36 40H12C8.68629 40 6 37.3137 6 34V14Z"
                    fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M24 19L26.4 24.0L31 24.6L27.5 28.0L28.4 32.5L24 30.3L19.6 32.5
                       L20.5 28.0L17 24.6L21.6 24.0L24 19Z"
                    fill="none" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M24 19L26.4 24.0L31 24.6L27.5 28.0L28.4 32.5L24 30.3L19.6 32.5
                       L20.5 28.0L17 24.6L21.6 24.0L24 19Z"
                    fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        """,
        "brightness": """
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <circle cx="24" cy="24" r="10" stroke="black" stroke-width="4"/>
              <line x1="24" y1="4"  x2="24" y2="10" stroke="black" stroke-width="4"/>
              <line x1="24" y1="38" x2="24" y2="44" stroke="black" stroke-width="4"/>
              <line x1="4"  y1="24" x2="10" y2="24" stroke="black" stroke-width="4"/>
              <line x1="38" y1="24" x2="44" y2="24" stroke="black" stroke-width="4"/>
              <line x1="8"  y1="8"  x2="12" y2="12" stroke="black" stroke-width="4"/>
              <line x1="36" y1="36" x2="40" y2="40" stroke="black" stroke-width="4"/>
              <line x1="8"  y1="40" x2="12" y2="36" stroke="black" stroke-width="4"/>
              <line x1="36" y1="12" x2="40" y2="8"  stroke="black" stroke-width="4"/>
              <circle cx="24" cy="24" r="10" stroke="white" stroke-width="2"/>
              <line x1="24" y1="4"  x2="24" y2="10" stroke="white" stroke-width="2"/>
              <line x1="24" y1="38" x2="24" y2="44" stroke="white" stroke-width="2"/>
              <line x1="4"  y1="24" x2="10" y2="24" stroke="white" stroke-width="2"/>
              <line x1="38" y1="24" x2="44" y2="24" stroke="white" stroke-width="2"/>
              <line x1="8"  y1="8"  x2="12" y2="12" stroke="white" stroke-width="2"/>
              <line x1="36" y1="36" x2="40" y2="40" stroke="white" stroke-width="2"/>
              <line x1="8"  y1="40" x2="12" y2="36" stroke="white" stroke-width="2"/>
              <line x1="36" y1="12" x2="40" y2="8"  stroke="white" stroke-width="2"/>
            </svg>
        """,
        "rotate": """
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M16 16 A13.3333 13.3333 0 1 1 32 32 M32 32 l5.3333 2.6667 M32 32 l2.6667 -6.6667"
                    fill="none" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M16 16 A13.3333 13.3333 0 1 1 32 32 M32 32 l5.3333 2.6667 M32 32 l2.6667 -6.6667"
                    fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        """,
        "fullscreen": """
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M14 6L6 6L6 14" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M34 6L42 6L42 14" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M14 42L6 42L6 34" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M34 42L42 42L42 34" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M14 6L6 6L6 14" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M34 6L42 6L42 14" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M14 42L6 42L6 34" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M34 42L42 42L42 34" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        """,
        "settings": """
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <line x1="8"  y1="12" x2="40" y2="12" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="30" cy="12" r="3" fill="none" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <line x1="8"  y1="24" x2="40" y2="24" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="14" cy="24" r="3" fill="none" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <line x1="8"  y1="36" x2="40" y2="36" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="24" cy="36" r="3" fill="none" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <line x1="8"  y1="12" x2="40" y2="12" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="30" cy="12" r="3" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <line x1="8"  y1="24" x2="40" y2="24" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="14" cy="24" r="3" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <line x1="8"  y1="36" x2="40" y2="36" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="24" cy="36" r="3" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        """,
        "close": """
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <line x1="12" y1="12" x2="36" y2="36" stroke="black" stroke-width="4" stroke-linecap="round"/>
              <line x1="36" y1="12" x2="12" y2="36" stroke="black" stroke-width="4" stroke-linecap="round"/>
              <line x1="12" y1="12" x2="36" y2="36" stroke="white" stroke-width="2" stroke-linecap="round"/>
              <line x1="36" y1="12" x2="12" y2="36" stroke="white" stroke-width="2" stroke-linecap="round"/>
            </svg>
        """,
        "empty_star": """
            <svg fill="none" width="32" height="32" viewBox="0 0 32 32"
                 xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
              <g transform="translate(2.4,2.4) scale(0.85)">
                <path d="
                  m18.6046 3.74448 2.2031 4.61977c.3411.686.9633 1.16835 1.6857 1.27553
                  l4.9274.69672c2.5387.3752 3.4963 3.101 1.5275 5.0854l-3.4531 3.5625
                  c-.5619.5573-.8228 1.3827-.6824 2.1866l.7761 5.0634c.4415 2.6261
                  -1.7703 4.4892-4.008 3.2887l-4.5355-2.4117c-.6321-.3323-1.3746-.3323
                  -2.0068 0l-4.5355 2.4117c-2.23762 1.1897-4.58605-.6169-3.9298-3.3512
                  l.76563-4.9531c.14048-.804-.12041-1.6293-.68233-2.1866l-3.52084-3.6884
                  c-1.98434-1.961-1.01123-4.6321 1.52743-5.0073l4.7462-.69672
                  c.72251-.10718 1.55151-.57881 1.88271-1.27553l2.2476-4.61977
                  c1.1439-2.32597 3.931-2.32597 5.0649 0z
                " fill="none" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
                <path d="
                  m18.6046 3.74448 2.2031 4.61977c.3411.686.9633 1.16835 1.6857 1.27553
                  l4.9274.69672c2.5387.3752 3.4963 3.101 1.5275 5.0854l-3.4531 3.5625
                  c-.5619.5573-.8228 1.3827-.6824 2.1866l.7761 5.0634c.4415 2.6261
                  -1.7703 4.4892-4.008 3.2887l-4.5355-2.4117c-.6321-.3323-1.3746-.3323
                  -2.0068 0l-4.5355 2.4117c-2.23762 1.1897-4.58605-.6169-3.9298-3.3512
                  l.76563-4.9531c.14048-.804-.12041-1.6293-.68233-2.1866l-3.52084-3.6884
                  c-1.98434-1.961-1.01123-4.6321 1.52743-5.0073l4.7462-.69672
                  c.72251-.10718 1.55151-.57881 1.88271-1.27553l2.2476-4.61977
                  c1.1439-2.32597 3.931-2.32597 5.0649 0z
                " fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </g>
            </svg>
        """,
        "filled_star": """
            <svg fill="none" width="32" height="32" viewBox="0 0 32 32"
                 xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
              <g transform="translate(2.4,2.4) scale(0.85)">
                <path d="
                  m18.6046 3.74448 2.2031 4.61977c.3411.686.9633 1.16835 1.6857 1.27553
                  l4.9274.69672c2.5387.3752 3.4963 3.101 1.5275 5.0854l-3.4531 3.5625
                  c-.5619.5573-.8228 1.3827-.6824 2.1866l.7761 5.0634c.4415 2.6261
                  -1.7703 4.4892-4.008 3.2887l-4.5355-2.4117c-.6321-.3323-1.3746-.3323
                  -2.0068 0l-4.5355 2.4117c-2.23762 1.1897-4.58605-.6169-3.9298-3.3512
                  l.76563-4.9531c.14048-.804-.12041-1.6293-.68233-2.1866l-3.52084-3.6884
                  c-1.98434-1.961-1.01123-4.6321 1.52743-5.0073l4.7462-.69672
                  c.72251-.10718 1.55151-.57881 1.88271-1.27553l2.2476-4.61977
                  c1.1439-2.32597 3.931-2.32597 5.0649 0z
                " fill="gold" stroke="black" stroke-width="0.8" stroke-linecap="round" stroke-linejoin="round"/>
              </g>
            </svg>
        """,
        "all_images": """
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="4" y="4" width="40" height="40" rx="6" fill="none" stroke="black" stroke-width="4"/>
              <rect x="4" y="4" width="40" height="40" rx="6" fill="none" stroke="white" stroke-width="2"/>
              <path d="M10 30 L18 20 L26 26 L32 22 L38 30" stroke="black" stroke-width="4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M10 30 L18 20 L26 26 L32 22 L38 30" stroke="white" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
              <circle cx="15" cy="15" r="3" fill="none" stroke="black" stroke-width="4"/>
              <circle cx="15" cy="15" r="3" fill="none" stroke="white" stroke-width="2"/>
            </svg>
        """,
        "menu": """
            <svg width="48" height="48" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" fill="none">
              <line x1="12" y1="14" x2="36" y2="14" stroke="black" stroke-width="5" stroke-linecap="round"/>
              <line x1="12" y1="24" x2="36" y2="24" stroke="black" stroke-width="5" stroke-linecap="round"/>
              <line x1="12" y1="34" x2="36" y2="34" stroke="black" stroke-width="5" stroke-linecap="round"/>
              <line x1="12" y1="14" x2="36" y2="14" stroke="white" stroke-width="3" stroke-linecap="round"/>
              <line x1="12" y1="24" x2="36" y2="24" stroke="white" stroke-width="3" stroke-linecap="round"/>
              <line x1="12" y1="34" x2="36" y2="34" stroke="white" stroke-width="3" stroke-linecap="round"/>
            </svg>
        """,
        "crop": """
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M36 42V16C36 14 34 12 32 12H6" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M36 42V16C36 14 34 12 32 12H6" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M14 4V30C14 32 16 34 18 34H44" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M14 4V30C14 32 16 34 18 34H44" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        """,
        "sharpness": """
        <svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" fill="none">
          <path d="M8 40 L22 40 L22 8 Z"
                fill="none" stroke="black" stroke-width="4"
                stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M8 40 L22 40 L22 8 Z"
                fill="none" stroke="white" stroke-width="2"
                stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M44 40 L30 40 L30 8 Z"
                fill="white" stroke="black" stroke-width="4"
                stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M44 40 L30 40 L30 8 Z"
                fill="white" stroke="white" stroke-width="2"
                stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        """,
        "compare": """
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M18 12 L8 24 L18 36" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M18 12 L8 24 L18 36" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M30 12 L40 24 L30 36" stroke="black" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M30 12 L40 24 L30 36" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        """
    }
    _cache = {}

    @classmethod
    def get_icon(cls, name: str, size: int = 48) -> QIcon:
        cache_key = (name, size)
        if cache_key in cls._cache:
            return cls._cache[cache_key]
        svg_str = cls._svg_strings.get(name)
        if not svg_str:
            print(f"[IconFactory] No SVG for icon '{name}'")
            icon = QIcon()
            cls._cache[cache_key] = icon
            return icon
        renderer = QSvgRenderer(QByteArray(svg_str.encode('utf-8')))
        high_res = size * 2
        pixmap = QPixmap(high_res, high_res)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        renderer.render(painter)
        painter.end()
        scaled_pixmap = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
        icon = QIcon(scaled_pixmap)
        cls._cache[cache_key] = icon
        return icon
