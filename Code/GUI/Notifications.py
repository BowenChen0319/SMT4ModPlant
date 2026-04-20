import sys

from PyQt6.QtCore import QObject, QPoint, QEvent, QPropertyAnimation, QEasingCurve, QTimer, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF, InfoBar as FluentInfoBar, TransparentToolButton


TOAST_WIDTH = 396
TOAST_MARGIN = 24
TOAST_GAP = 12


def _append_log(parent, level: str, title: str, content: str):
    """Mirror UI notifications into the log page when available."""
    try:
        if parent is not None and hasattr(parent, "window"):
            main = parent.window()
            if hasattr(main, "log_page") and hasattr(main.log_page, "append_log"):
                message = f"[{level}] {title}"
                if content:
                    message = f"{message}: {content}"
                main.log_page.append_log(message)
    except Exception:
        pass


def _use_custom_toast() -> bool:
    """Use the custom banner implementation on macOS where Fluent InfoBar proved unstable."""
    return sys.platform == "darwin"


def _resolve_window(parent) -> QWidget | None:
    """Find the top-level window used to host non-modal banners."""
    if parent is not None and hasattr(parent, "window"):
        window = parent.window()
        if isinstance(window, QWidget):
            return window

    active = QApplication.activeWindow()
    return active if isinstance(active, QWidget) else None


class ToastBanner(QFrame):
    """Right-top in-app notification banner with light slide animations."""

    def __init__(self, host_manager, level: str, title: str, content: str, duration: int, closable: bool):
        super().__init__(host_manager.window)
        self.host_manager = host_manager
        self.level = level
        self.duration = max(int(duration or 0), 0)
        self._closing = False

        self.setObjectName("safeToastBanner")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(TOAST_WIDTH)

        palette = self._palette(level)
        self._shadow_color = QColor(0, 0, 0, 46)
        self._shadow_glow = QColor(0, 0, 0, 16)

        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(10, 8, 10, 12)
        container_layout.setSpacing(0)

        self.panel = QFrame(self)
        self.panel.setObjectName("safeToastPanel")
        self.panel.setStyleSheet(
            f"""
            QFrame#safeToastPanel {{
                background-color: rgba(15, 21, 27, 0.97);
                border: 1px solid {palette['border']};
                border-radius: 20px;
            }}
            QLabel {{
                background: transparent;
            }}
            """
        )
        container_layout.addWidget(self.panel)

        content_layout = QHBoxLayout(self.panel)
        content_layout.setContentsMargins(18, 16, 14, 16)
        content_layout.setSpacing(12)

        icon_badge = QLabel(palette["icon"], self.panel)
        icon_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_badge.setFixedSize(40, 40)
        icon_badge.setStyleSheet(
            f"""
            QLabel {{
                color: {palette['icon_fg']};
                background-color: {palette['icon_bg']};
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 20px;
                font-size: 18px;
                font-weight: 700;
            }}
            """
        )
        content_layout.addWidget(icon_badge, 0, Qt.AlignmentFlag.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(6)

        title_label = QLabel(title or palette["title"], self.panel)
        title_label.setStyleSheet("color: #F5F8FB; font-size: 15px; font-weight: 700;")
        title_label.setWordWrap(True)
        text_layout.addWidget(title_label)

        if content:
            content_label = QLabel(content, self.panel)
            content_label.setStyleSheet("color: #C7D2DD; font-size: 12px; line-height: 1.4;")
            content_label.setWordWrap(True)
            content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            text_layout.addWidget(content_label)

        chip = QLabel(palette["chip"], self.panel)
        chip.setStyleSheet(
            f"""
            QLabel {{
                color: {palette['chip_fg']};
                background-color: {palette['chip_bg']};
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 999px;
                padding: 3px 10px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.06em;
            }}
            """
        )
        text_layout.addWidget(chip, 0, Qt.AlignmentFlag.AlignLeft)
        content_layout.addLayout(text_layout, 1)

        close_btn = TransparentToolButton(self.panel)
        close_btn.setIcon(FIF.CLOSE)
        close_btn.setFixedSize(30, 30)
        close_btn.setVisible(bool(closable))
        close_btn.clicked.connect(self.close_with_animation)
        close_btn.setStyleSheet(
            """
            TransparentToolButton {
                border-radius: 15px;
                background: transparent;
            }
            TransparentToolButton:hover {
                background: rgba(255, 255, 255, 0.08);
            }
            """
        )
        content_layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignTop)

        self.adjustSize()

        self.slide_anim = QPropertyAnimation(self, b"pos", self)
        self.slide_anim.setDuration(240)
        self.slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.close_with_animation)

    @staticmethod
    def _palette(level: str):
        if level == "error":
            return {
                "border": "rgba(213, 96, 113, 0.68)",
                "icon_bg": "rgba(95, 27, 40, 0.92)",
                "icon_fg": "#FFD7DE",
                "icon": "!",
                "title": "Error",
                "chip": "ERROR",
                "chip_bg": "rgba(213, 96, 113, 0.18)",
                "chip_fg": "#FFC6D0",
            }
        if level == "warning":
            return {
                "border": "rgba(226, 170, 84, 0.62)",
                "icon_bg": "rgba(83, 58, 20, 0.92)",
                "icon_fg": "#FFE0A8",
                "icon": "!",
                "title": "Warning",
                "chip": "NOTICE",
                "chip_bg": "rgba(226, 170, 84, 0.18)",
                "chip_fg": "#FFDEAA",
            }
        return {
            "border": "rgba(87, 182, 123, 0.64)",
            "icon_bg": "rgba(24, 68, 46, 0.92)",
            "icon_fg": "#D8F6E2",
            "icon": "✓",
            "title": "Completed",
            "chip": "SUCCESS",
            "chip_bg": "rgba(87, 182, 123, 0.18)",
            "chip_fg": "#C8F0D6",
        }

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        shadow_rect = self.panel.geometry().translated(0, 5)
        painter.setBrush(self._shadow_color)
        painter.drawRoundedRect(shadow_rect.adjusted(4, 2, -4, 4), 22, 22)

        painter.setBrush(self._shadow_glow)
        painter.drawRoundedRect(shadow_rect.adjusted(-1, -2, 1, 6), 24, 24)

        super().paintEvent(event)

    def show_in_place(self, target: QPoint, animate: bool = True):
        start = QPoint(self.parentWidget().width() + self.width(), target.y())
        if not self.isVisible():
            self.move(start if animate else target)
            self.show()
            self.raise_()

        self.slide_anim.stop()
        self.slide_anim.setStartValue(self.pos())
        self.slide_anim.setEndValue(target)
        if animate:
            self.slide_anim.start()
        else:
            self.move(target)

        if self.duration > 0 and not self._closing:
            self.hide_timer.start(self.duration)

    def close_with_animation(self):
        if self._closing:
            return

        self._closing = True
        self.hide_timer.stop()

        end = QPoint(self.parentWidget().width() + self.width() + 12, self.y())
        self.slide_anim.stop()
        self.slide_anim.setStartValue(self.pos())
        self.slide_anim.setEndValue(end)
        try:
            self.slide_anim.finished.disconnect()
        except Exception:
            pass
        self.slide_anim.finished.connect(self._finalize_close)
        self.slide_anim.start()

    def _finalize_close(self):
        try:
            self.slide_anim.finished.disconnect(self._finalize_close)
        except Exception:
            pass

        self.hide()
        self.host_manager.remove_toast(self)
        self.deleteLater()


class ToastHost(QObject):
    """Keep a stack of banners aligned to the top-right corner of one window."""

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.window = window
        self.toasts: list[ToastBanner] = []
        self.window.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.window and event.type() in {QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show}:
            self.reposition_toasts(animate=False)
        return super().eventFilter(obj, event)

    def show_toast(self, level: str, title: str, content: str, duration: int, closable: bool):
        toast = ToastBanner(self, level, title, content, duration, closable)
        self.toasts.insert(0, toast)
        self.reposition_toasts(animate=True)
        return toast

    def remove_toast(self, toast: ToastBanner):
        if toast in self.toasts:
            self.toasts.remove(toast)
            self.reposition_toasts(animate=True)

    def reposition_toasts(self, animate: bool):
        y = TOAST_MARGIN
        width = self.window.width()
        for toast in self.toasts:
            if toast._closing:
                continue
            target = QPoint(max(TOAST_MARGIN, width - toast.width() - TOAST_MARGIN), y)
            toast.show_in_place(target, animate=animate)
            y += toast.height() + TOAST_GAP


def _show_custom_toast(level: str, title: str, content: str, parent, duration: int, closable: bool):
    window = _resolve_window(parent)
    if window is None:
        if level == "error":
            QMessageBox.critical(parent, title or "Error", content or "")
        elif level == "warning":
            QMessageBox.warning(parent, title or "Warning", content or "")
        return None

    host = getattr(window, "_safe_toast_host", None)
    if host is None:
        host = ToastHost(window)
        setattr(window, "_safe_toast_host", host)
    return host.show_toast(level=level, title=title, content=content, duration=duration, closable=closable)


class SafeInfoBar:
    """Drop-in replacement for qfluentwidgets.InfoBar with a custom macOS-safe banner."""

    @staticmethod
    def success(*args, **kwargs):
        title = kwargs.get("title", "")
        content = kwargs.get("content", "")
        parent = kwargs.get("parent")
        duration = kwargs.get("duration", 3200)
        is_closable = kwargs.get("isClosable", True)
        _append_log(parent, "SUCCESS", title, content)

        if _use_custom_toast():
            return _show_custom_toast("success", title, content, parent, duration, is_closable)

        return FluentInfoBar.success(*args, **kwargs)

    @staticmethod
    def warning(*args, **kwargs):
        title = kwargs.get("title", "")
        content = kwargs.get("content", "")
        parent = kwargs.get("parent")
        duration = kwargs.get("duration", 5000)
        is_closable = kwargs.get("isClosable", True)
        _append_log(parent, "WARNING", title, content)

        if _use_custom_toast():
            return _show_custom_toast("warning", title, content, parent, duration, is_closable)

        return FluentInfoBar.warning(*args, **kwargs)

    @staticmethod
    def error(*args, **kwargs):
        title = kwargs.get("title", "")
        content = kwargs.get("content", "")
        parent = kwargs.get("parent")
        duration = kwargs.get("duration", 7000)
        is_closable = kwargs.get("isClosable", True)
        _append_log(parent, "ERROR", title, content)

        if _use_custom_toast():
            return _show_custom_toast("error", title, content, parent, duration, is_closable)

        return FluentInfoBar.error(*args, **kwargs)
