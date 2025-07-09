import sys
import os
import tempfile
import json
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, QCoreApplication, QEvent
from ui_components.ui_base_full import UIBaseFull
from ui_components.ui_title_text import UITitleText
from ui_components.ui_header_text import UIHeaderText
from ui_components.ui_image import UIImage
from ui_components.ui_button import UIButton



class ResizeHandler(QObject):
    def __init__(self, overlay, img_label, buttons):
        super().__init__(overlay)
        self.overlay = overlay
        self.img_label = img_label
        self.buttons = buttons

    def eventFilter(self, obj, event):
        if obj is self.overlay and event.type() == QEvent.Resize:
            self.position_elements()
        return False

    def position_elements(self):
        W = self.overlay.width()
        H = self.overlay.height()
        pix = self.img_label.pixmap()
        if pix:
            pix_h = pix.height()
            pix_y = (H - pix_h) // 2
            bottom = pix_y + pix_h
        else:
            bottom = H // 2
        spacing = 10
        for btn in self.buttons:
            btn.adjustSize()
        widths = [btn.width() for btn in self.buttons]
        total_width = sum(widths) + spacing * (len(self.buttons) - 1)
        x = (W - total_width) // 2
        y = bottom + 50
        for btn, w in zip(self.buttons, widths):
            btn.move(x, y)
            x += w + spacing



def main():
    app = QApplication.instance() or QApplication(sys.argv)
    base = UIBaseFull()
    overlay = base.primary_overlay
    title_label = UITitleText("Welcome", parent=overlay)
    header_label = UIHeaderText("Select your preferred web browser.", parent=overlay)
    img_label = UIImage("browser_selection.png", parent=overlay)
    img_label.lower()
    browser_options = [
        ("Chrome",              "google-chrome-x64", (251, 191, 14)),
        ("Edge",                "microsoft-edge",    (44, 195, 193)),
        ("Brave (Recommended)", "brave",             (255, 47, 0)),
        ("Firefox",             "firefox",           (89, 58, 177)),
        ("LibreWolf",           "librewolf",         (0, 174, 255)),
    ]
    buttons = []
    for label, pkg_id, color in browser_options:
        btn = UIButton(label, color, parent=overlay)
        def make_cb(p=pkg_id):
            def cb():
                temp_root = os.environ.get('TEMP', tempfile.gettempdir())
                dir_path = os.path.join(temp_root, 'talon')
                os.makedirs(dir_path, exist_ok=True)
                path = os.path.join(dir_path, 'browser_choice.json')
                with open(path, 'w') as f:
                    json.dump({'browser': p}, f)
                QCoreApplication.quit()
            return cb
        btn.clicked.connect(make_cb())
        buttons.append(btn)
    handler = ResizeHandler(overlay, img_label, buttons)
    overlay.installEventFilter(handler)
    handler.position_elements()
    title_label.raise_()
    header_label.raise_()
    for b in buttons:
        b.raise_()
    base.show()
    sys.exit(app.exec_())



if __name__ == "__main__":
    main()
