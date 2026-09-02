from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = "—", accent: str = "#27d3a2"):
        super().__init__()
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        title_label = QLabel(title)
        title_label.setProperty("muted", True)
        self.value = QLabel(value)
        self.value.setStyleSheet(f"font-size: 23px; font-weight: 700; color: {accent};")
        layout.addWidget(title_label)
        layout.addWidget(self.value)


class TemperatureChart(QWidget):
    """Dependency-free Qt chart for air and cargo temperature history."""
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(240)
        self.air: list[float] = []
        self.cargo: list[float | None] = []
        self.label = "温度趋势"

    def set_data(self, air: list[float], cargo: list[float | None], label: str = "温度趋势") -> None:
        self.air, self.cargo, self.label = air[-100:], cargo[-100:], label
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#151d29"))
        painter.setPen(QColor("#dce7f3")); painter.setFont(QFont("Microsoft YaHei", 10, 600))
        painter.drawText(16, 24, self.label)
        left, top, right, bottom = 48, 42, self.width()-18, self.height()-30
        painter.setPen(QPen(QColor("#293648"), 1))
        for i in range(5):
            y = top + (bottom-top)*i/4
            painter.drawLine(left, int(y), right, int(y))
        values = self.air + [x for x in self.cargo if x is not None]
        if len(self.air) < 2 or not values:
            painter.setPen(QColor("#728198")); painter.drawText(left, (top+bottom)//2, "模拟运行后显示温度采样")
            return
        lo, hi = min(values)-2, max(values)+2
        if hi-lo < 1: hi = lo+1
        painter.setFont(QFont("Microsoft YaHei", 8)); painter.setPen(QColor("#728198"))
        painter.drawText(4, top+5, f"{hi:.0f}°") ; painter.drawText(4, bottom, f"{lo:.0f}°")
        def path_for(series):
            path = QPainterPath(); started = False
            for i, value in enumerate(series):
                if value is None: continue
                x = left + (right-left)*i/max(1,len(series)-1)
                y = bottom - (bottom-top)*(value-lo)/(hi-lo)
                if not started: path.moveTo(QPointF(x,y)); started=True
                else: path.lineTo(QPointF(x,y))
            return path
        painter.setPen(QPen(QColor("#24a8ff"), 2)); painter.drawPath(path_for(self.air))
        painter.setPen(QPen(QColor("#ffb547"), 2)); painter.drawPath(path_for(self.cargo))
        painter.setPen(QColor("#24a8ff")); painter.drawText(right-150, 20, "— 空气")
        painter.setPen(QColor("#ffb547")); painter.drawText(right-75, 20, "— 核心")

