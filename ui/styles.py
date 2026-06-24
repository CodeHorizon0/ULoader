QSS = """
QWidget#DownloaderUI {
    background: #1b1d22;
}

QLabel#sectionTitle,
QLabel#subsectionTitle {
    font-weight: 700;
    color: #f2f4f8;
    padding-top: 2px;
}

QLabel#sectionTitle {
    font-size: 14px;
}

QLabel#subsectionTitle {
    font-size: 12px;
    color: #cfd5df;
}

QLineEdit#inputField,
QComboBox#selectField {
    padding: 5px 6px;
    border: 1px solid #353a43;
    border-radius: 10px;
    background: #23262d;
    color: #f2f4f8;
}

QLineEdit#inputField:focus,
QComboBox#selectField:focus {
    border: 1px solid #4f8cff;
}

QLineEdit#inputField:disabled,
QComboBox#selectField:disabled,
QTextEdit#statusLog:disabled,
QTextEdit#metaPreview:disabled {
    opacity: 0.78;
}

QComboBox#selectField::drop-down {
    border: 0;
    width: 22px;
}

QComboBox#selectField QAbstractItemView {
    background: #23262d;
    color: #f2f4f8;
    selection-background-color: #4f8cff;
    outline: 0;
}

QPushButton#downloadButton {
    padding: 3px 6px;
    font-weight: 700;
    border-radius: 10px;
    background-color: #4f8cff;
    color: white;
    border: none;
    min-height: 26px;
}

QPushButton#downloadButton:hover {
    background-color: #6599ff;
}

QPushButton#downloadButton:pressed {
    background-color: #3f78df;
}

QPushButton#downloadButton:disabled {
    background-color: rgba(79, 140, 255, 120);
    color: rgba(255, 255, 255, 180);
}

QPushButton#pauseButton,
QPushButton#cancelButton {
    padding: 3px 6px;
    font-weight: 700;
    border-radius: 10px;
    border: none;
    color: white;
    min-height: 26px;
}

QPushButton#pauseButton {
    background-color: #3b4353;
}

QPushButton#pauseButton:hover {
    background-color: #4a5567;
}

QPushButton#pauseButton:pressed {
    background-color: #303846;
}

QPushButton#cancelButton {
    background-color: #b34b4b;
}

QPushButton#cancelButton:hover {
    background-color: #c95a5a;
}

QPushButton#cancelButton:pressed {
    background-color: #953e3e;
}

QPushButton#pauseButton:disabled,
QPushButton#cancelButton:disabled {
    background-color: rgba(90, 90, 90, 150);
    color: rgba(255, 255, 255, 170);
}

QProgressBar#progressBar {
    border: 1px solid #353a43;
    border-radius: 10px;
    text-align: center;
    background: #23262d;
    height: 16px;
    color: #f2f4f8;
}

QProgressBar#progressBar::chunk {
    border-radius: 9px;
    background: #4f8cff;
}

QTextEdit#statusLog,
QTextEdit#metaPreview {
    border: 1px solid #353a43;
    border-radius: 10px;
    background: #23262d;
    color: #f2f4f8;
}

QTextEdit#statusLog {
    min-height: 170px;
}

QTextEdit#metaPreview {
    min-height: 112px;
}

QFrame#metaCard {
    border: 1px solid #353a43;
    border-radius: 12px;
    background: #20232a;
}

QLabel#thumbnailLabel {
    border: 1px solid #353a43;
    border-radius: 10px;
    background: #171a20;
    color: #aab2bf;
    padding: 3px;
}

QLabel#checkLabel {
    padding: 0 4px;
    color: #aab2bf;
}

QScrollBar:vertical {
    background: #1b1d22;
    width: 12px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #3a414d;
    min-height: 24px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #4c5563;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}
"""

LAYOUT = {
    "spacing": 4,
    "margins": (5, 5, 5, 5),
}
