"""Reusable PyQt widgets: overlays, combo boxes, sliders, drag overlay."""
import os
from PyQt6.QtWidgets import (
    QWidget,
    QComboBox,
    QHBoxLayout,
    QListView,
    QStyledItemDelegate,
    QSlider,
    QStyle,
)
from PyQt6.QtGui import QBrush, QKeyEvent, QMouseEvent
from PyQt6.QtCore import Qt, QPoint, QTimer, QEvent, pyqtSignal
from PyQt6.QtGui import QGuiApplication


ALLOWED_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif')


# ------------------------------------------------------------------------
# Base Overlay
# ------------------------------------------------------------------------
class BaseOverlay(QWidget):
    def __init__(self, parent=None, overlay_name="BaseOverlay", bg_color="rgba(0, 0, 0, 150)"):
        super().__init__(parent)
        self.setObjectName(overlay_name)
        if parent:
            self.setGeometry(parent.rect())
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet(f"#{overlay_name} {{ background-color: {bg_color}; }}")


# ------------------------------------------------------------------------
# Filter Combo boxes / sorting
# ------------------------------------------------------------------------
class AlternateComboBox(QComboBox):
    def __init__(self, options_list, current_value, parent=None):
        super().__init__(parent)
        self.all_options = options_list
        self.current_value = current_value
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.refreshItems()

    def refreshItems(self):
        self.clear()
        for label, value in self.all_options:
            if value != self.current_value:
                self.addItem(label, value)
        current_label = next((label for label, value in self.all_options if value == self.current_value), "")
        self.setEditText(current_label)

    def showPopup(self):
        self.refreshItems()
        super().showPopup()

    def setCurrentValue(self, new_value):
        self.current_value = new_value
        current_label = next((label for label, value in self.all_options if value == self.current_value), "")
        self.setEditText(current_label)


class SortingBar(QWidget):
    def __init__(self, parent=None, t=None, current_criterion="file_name", current_order=True):
        super().__init__(parent)
        self.t = t or {}
        self.criterion_combo = QComboBox(self)
        self.order_combo = QComboBox(self)
        criterion_options = [
            (self.t.get("sort_file_name", "Name"), "file_name"),
            (self.t.get("sort_date_modified", "Date Modified"), "date_modified"),
            (self.t.get("sort_size", "Size"), "size")
        ]
        for label, value in criterion_options:
            self.criterion_combo.addItem(label, value)
        index = next((i for i, (_, val) in enumerate(criterion_options) if val == current_criterion), 0)
        self.criterion_combo.setCurrentIndex(index)
        self.order_combo.addItem(self.t.get("sort_ascending", "Ascending ↑"), True)
        self.order_combo.addItem(self.t.get("sort_descending", "Descending ↓"), False)
        index = 0 if current_order else 1
        self.order_combo.setCurrentIndex(index)
        style = """
        QComboBox {
            background-color: #323232;
            color: white;
            font-size: 16px;
            padding: 6px 10px;
            border: 1px solid #555;
            border-radius: 6px;
        }
        QComboBox::drop-down {
            border: none;
            width: 24px;
        }
        QComboBox QAbstractItemView {
            background-color: #3a3a3a;
            selection-background-color: transparent;
            color: white;
            border: 1px solid #444;
        }
        SortingBar {
            background-color: transparent;
            padding: 2px;
            border-radius: 6px;
        }
        SortingBar:hover {
            background-color: #3a3a3a;
        }
        """
        self.criterion_combo.setStyleSheet(style)
        self.order_combo.setStyleSheet(style)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.criterion_combo)
        layout.addWidget(self.order_combo)
        self.setLayout(layout)


# ------------------------------------------------------------------------
# Drag Settings
# ------------------------------------------------------------------------
class DraggableContainer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.drag_offset = None
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None:
            new_pos = self.mapToParent(event.position().toPoint() - self.drag_offset)
            self.move(new_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = None
        super().mouseReleaseEvent(event)


class NoHighlightDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.state &= ~QStyle.StateFlag.State_Selected
        option.state &= ~QStyle.StateFlag.State_HasFocus
        option.backgroundBrush = QBrush(Qt.GlobalColor.transparent)
        super().paint(painter, option, index)


class OverlayComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_container = None
        self._custom_popup = None

    def showPopup(self):
        if self._popup_container is not None:
            self.hidePopup()
            return
        popup_view = QListView()
        popup_view.setModel(self.model())
        popup_view.setStyleSheet("""
        QListView {
            background-color: #222;
            color: white;
            border: 1px solid #444;
            border-radius: 6px;
            padding: 4px;
            font-size: 15px;
        }
        QListView::item {
            background-color: transparent;
            padding: 6px 10px;
        }
        QListView::item:hover,
        QListView::item:selected {
            background-color: #0078D7;
        }
        """)
        popup_view.setItemDelegate(NoHighlightDelegate())
        popup_view.clicked.connect(lambda index: self._on_item_clicked(index))
        parent_window = self.window()
        self._popup_container = BaseOverlay(
            parent=parent_window,
            overlay_name="ComboPopup",
            bg_color="transparent"
        )
        self._popup_container.setGeometry(parent_window.rect())
        container_width = self.width()
        item_count = self.count()
        row_height = popup_view.sizeHintForRow(0) if item_count > 0 else 20
        container_height = row_height * min(10, item_count) + 2 * popup_view.frameWidth()
        global_pos = self.mapToGlobal(QPoint(0, self.height()))
        overlay_top_left = self._popup_container.mapFromGlobal(global_pos)
        screen = QGuiApplication.primaryScreen()
        available_rect = screen.availableGeometry() if screen else parent_window.geometry()
        global_bottom = global_pos.y() + container_height
        if global_bottom > available_rect.bottom():
            global_pos = self.mapToGlobal(QPoint(0, -container_height))
            overlay_top_left = self._popup_container.mapFromGlobal(global_pos)
        popup_view.setParent(self._popup_container)
        popup_view.setGeometry(overlay_top_left.x(), overlay_top_left.y(),
                               container_width, container_height)
        popup_view.show()
        popup_view.setItemDelegate(NoHighlightDelegate())
        self._custom_popup = popup_view
        self._popup_container.show()
        self._popup_container.raise_()
        popup_view.setFocus(Qt.FocusReason.MouseFocusReason)

        def overlay_mousePressEvent(event):
            if not popup_view.geometry().contains(event.pos()):
                self.hidePopup()
                event.accept()
            else:
                event.ignore()
        self._popup_container.mousePressEvent = overlay_mousePressEvent

    def hidePopup(self):
        if self._popup_container:
            self._popup_container.hide()
            self._popup_container.deleteLater()
            self._popup_container = None
            self._custom_popup = None

    def _on_item_clicked(self, index):
        self.setCurrentIndex(index.row())
        self.activated.emit(index.row())
        self.hidePopup()

    def eventFilter(self, obj, event):
        if obj is self and event.type() == QEvent.Type.MouseButtonPress:
            if self._popup_container is not None:
                self.hidePopup()
                return True
        return super().eventFilter(obj, event)


class SmoothRotationSlider(QSlider):
    floatValueChanged = pyqtSignal(float)

    def __init__(self, orientation: Qt.Orientation = Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setRange(-1800, 1800)
        self.setSingleStep(1)
        self.setTickInterval(450)
        self.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._popup_container = None
        self._custom_popup = None

    def value(self) -> float:
        return super().value() / 10.0

    def setValue(self, value: float):
        super().setValue(int(round(value * 10)))

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Up:
            self.setValue(self.value() + 1.0)
            event.accept()
        elif event.key() == Qt.Key.Key_Down:
            self.setValue(self.value() - 1.0)
            event.accept()
        else:
            super().keyPressEvent(event)
            self.floatValueChanged.emit(self.value())

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.floatValueChanged.emit(self.value())

    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)
        self.floatValueChanged.emit(self.value())


# ------------------------------------------------------------------------
# Drag-overlay for drop targets
# ------------------------------------------------------------------------
class MyDragOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setStyleSheet("background: transparent; border: none;")
        self.setGeometry(parent.rect())
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

    def _urls_allowed(self, urls):
        for url in urls:
            path = url.toLocalFile().lower()
            if path.endswith(ALLOWED_EXTENSIONS):
                return True
        return False

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and self._urls_allowed(event.mimeData().urls()):
            if self.hide_timer.isActive():
                self.hide_timer.stop()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() and self._urls_allowed(event.mimeData().urls()):
            if self.hide_timer.isActive():
                self.hide_timer.stop()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.hide_timer.start(100)
        event.accept()

    def dropEvent(self, event):
        if event.mimeData().hasUrls() and self._urls_allowed(event.mimeData().urls()):
            event.acceptProposedAction()
            urls = event.mimeData().urls()
            if len(urls) > 1:
                paths = [url.toLocalFile() for url in urls
                         if url.toLocalFile().lower().endswith(ALLOWED_EXTENSIONS)]
                if paths:
                    folder = os.path.dirname(paths[0])
                    self.window().load_directory(folder, selected_file=paths[0])
            else:
                for url in urls:
                    path = url.toLocalFile()
                    if not path.lower().endswith(ALLOWED_EXTENSIONS):
                        continue
                    main = self.window()
                    if os.path.isdir(path):
                        main.load_directory(path)
                    else:
                        main.load_directory(os.path.dirname(path), selected_file=path)
            self.hide()
        else:
            event.ignore()
