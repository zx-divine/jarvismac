import math
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient, QFont
from PySide6.QtWidgets import QWidget

class CoreOrb(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumWidth(210)
        self.setFixedHeight(195)
        self.state, self.level, self.phase = "idle", 0.0, 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(66)

    def tick(self):
        if self.isVisible() and not self.window().isMinimized():
            self.phase = (self.phase + (0.15 if self.state == "sleeping" else 1)) % 10000
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        painter.translate(center)
        radius = min(self.width(), self.height()) * 0.36
        cyan = QColor("#ff667e" if self.state == "error" else "#235477" if self.state == "sleeping" else "#30dfff")
        pulse = math.sin(self.phase * 0.07)
        glow = QRadialGradient(0, 0, radius)
        glow.setColorAt(0, QColor(12, 80, 107, 180))
        glow.setColorAt(0.65, QColor(8, 32, 55, 110))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QRectF(-radius, -radius, radius * 2, radius * 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for index, scale in enumerate((1, 0.85, 0.69)):
            r = radius * scale + pulse * 2
            color = QColor(cyan)
            color.setAlpha(190 - index * 35)
            painter.setPen(QPen(color, 1.5 if index else 2))
            rotation = self.phase * (4 if self.state == "thinking" else 0.5) * (1 if index % 2 == 0 else -1)
            painter.drawArc(QRectF(-r, -r, r * 2, r * 2), int(rotation * 16), 240 * 16)
        painter.setPen(QPen(cyan, 2))
        for index in range(48):
            angle = index * math.pi / 24
            if self.state == "listening":
                amplitude = self.level * (6 + 12 * abs(math.sin(angle * 3 + self.phase * 0.2)))
            elif self.state == "speaking":
                amplitude = 5 + 8 * abs(math.sin(index * 0.6 + self.phase * 0.3))
            else:
                amplitude = 4
            r1, r2 = radius * 1.10, radius * 1.10 + amplitude
            painter.drawLine(int(math.cos(angle) * r1), int(math.sin(angle) * r1), int(math.cos(angle) * r2), int(math.sin(angle) * r2))
        painter.setFont(QFont("Segoe UI", 21, QFont.Weight.Light))
        painter.drawText(QRectF(-radius, -25, radius * 2, 50), Qt.AlignmentFlag.AlignCenter, "J A R V I S")
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(QRectF(-radius, 22, radius * 2, 24), Qt.AlignmentFlag.AlignCenter, self.state.upper())
