from __future__ import annotations

import sys
from typing import NoReturn

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from ui.dark_theme import apply_dark_theme
from ui.ui import DownloaderUI
from utils.resource_path import resource_path


def main() -> NoReturn:
    app = QApplication(sys.argv)
    app.setApplicationName("ULoader")
    app.setOrganizationName("ULoader")
    app.setApplicationDisplayName("ULoader")
    app.setWindowIcon(QIcon(resource_path("icon.ico")))

    apply_dark_theme(app)

    window = DownloaderUI()
    window.show()

    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
