"""Schematic export: PNG, SVG, PDF."""
from __future__ import annotations

from PyQt6.QtCore import QRectF, QSizeF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QGraphicsScene


def _scene_rect(scene: QGraphicsScene, margin: float = 40.0) -> QRectF:
    rect = scene.itemsBoundingRect()
    if rect.isEmpty():
        rect = QRectF(-200, -200, 400, 400)
    return rect.adjusted(-margin, -margin, margin, margin)


def _suppress_grid(scene: QGraphicsScene, suppress: bool) -> None:
    """Temporarily hide the grid background on CircuitScene instances."""
    if hasattr(scene, "_show_grid"):
        scene._show_grid = not suppress  # type: ignore[assignment]


def export_png(scene: QGraphicsScene, filepath: str, dpi: int = 150) -> None:
    """Render scene to a PNG file (no grid lines)."""
    _suppress_grid(scene, True)
    try:
        rect = _scene_rect(scene)
        scale = dpi / 72.0
        w = int(rect.width() * scale)
        h = int(rect.height() * scale)
        image = QImage(w, h, QImage.Format.Format_ARGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.render(painter, QRectF(0, 0, w, h), rect)
        painter.end()
        if not image.save(filepath):
            raise OSError(f"Failed to save PNG to {filepath}")
    finally:
        _suppress_grid(scene, False)


def export_svg(scene: QGraphicsScene, filepath: str) -> None:
    """Render scene to an SVG file (no grid lines)."""
    from PyQt6.QtSvg import QSvgGenerator
    _suppress_grid(scene, True)
    try:
        rect = _scene_rect(scene)
        generator = QSvgGenerator()
        generator.setFileName(filepath)
        generator.setSize(rect.size().toSize())
        generator.setViewBox(rect)
        generator.setTitle("Xuircit Schematic")
        painter = QPainter(generator)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.render(painter, rect, rect)
        painter.end()
    finally:
        _suppress_grid(scene, False)


def export_pdf(scene: QGraphicsScene, filepath: str) -> None:
    """Render scene to a PDF file (no grid lines)."""
    from PyQt6.QtGui import QPdfWriter, QPageSize
    _suppress_grid(scene, True)
    try:
        rect = _scene_rect(scene)
        writer = QPdfWriter(filepath)
        writer.setResolution(150)
        page_size = QSizeF(rect.width(), rect.height())
        writer.setPageSize(QPageSize(page_size, QPageSize.Unit.Point))
        painter = QPainter(writer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.render(painter, QRectF(0, 0, rect.width(), rect.height()), rect)
        painter.end()
    finally:
        _suppress_grid(scene, False)
