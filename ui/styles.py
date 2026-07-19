def load_stylesheet() -> str:
    return """
    * {
        font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
        font-size: 13px;
    }

    #centralWidget {
        background-color: #f5f7fa;
    }

    #sidebar {
        background-color: #2c3e50;
        color: #ecf0f1;
        border: none;
        outline: none;
        padding: 10px 0;
    }

    #sidebar::item {
        padding: 14px 20px;
        color: #bdc3c7;
        border-left: 4px solid transparent;
        font-size: 14px;
    }

    #sidebar::item:hover {
        background-color: #34495e;
        color: #ffffff;
    }

    #sidebar::item:selected {
        background-color: #1abc9c;
        color: #ffffff;
        border-left: 4px solid #16a085;
    }

    #contentStack {
        background-color: #f5f7fa;
    }

    #statusBar {
        background-color: #ffffff;
        border-top: 1px solid #e0e6ed;
        padding: 4px 12px;
    }

    #statusLabel {
        color: #66788a;
    }

    #runBtn {
        background-color: #1abc9c;
        color: white;
        border: none;
        padding: 6px 18px;
        border-radius: 4px;
        font-weight: bold;
    }

    #runBtn:hover {
        background-color: #16a085;
    }

    #runBtn:disabled {
        background-color: #95a5a6;
    }

    .page-content {
        padding: 24px;
    }

    .page-title {
        font-size: 22px;
        font-weight: bold;
        color: #2c3e50;
        margin-bottom: 4px;
    }

    .page-subtitle {
        font-size: 13px;
        color: #7f8c8d;
        margin-bottom: 20px;
    }

    .card {
        background-color: #ffffff;
        border-radius: 8px;
        border: 1px solid #e8ecef;
        padding: 20px;
    }

    .card-title {
        font-size: 15px;
        font-weight: bold;
        color: #2c3e50;
        margin-bottom: 12px;
    }

    .stat-card {
        background-color: #ffffff;
        border-radius: 8px;
        border: 1px solid #e8ecef;
        padding: 20px;
    }

    .stat-value {
        font-size: 28px;
        font-weight: bold;
        color: #1abc9c;
    }

    .stat-label {
        font-size: 13px;
        color: #7f8c8d;
        margin-top: 4px;
    }

    QPushButton {
        background-color: #ffffff;
        color: #2c3e50;
        border: 1px solid #dcdfe6;
        border-radius: 5px;
        padding: 8px 16px;
        cursor: pointer;
    }

    QPushButton:hover {
        background-color: #f5f7fa;
        border-color: #1abc9c;
        color: #1abc9c;
    }

    QPushButton:pressed {
        background-color: #e8f5f2;
    }

    QPushButton.primary {
        background-color: #1abc9c;
        color: white;
        border: 1px solid #1abc9c;
    }

    QPushButton.primary:hover {
        background-color: #16a085;
        border-color: #16a085;
        color: white;
    }

    QPushButton.danger {
        background-color: #e74c3c;
        color: white;
        border: 1px solid #e74c3c;
    }

    QPushButton.danger:hover {
        background-color: #c0392b;
        border-color: #c0392b;
        color: white;
    }

    QLineEdit, QTextEdit, QSpinBox, QComboBox, QTimeEdit {
        background-color: #ffffff;
        border: 1px solid #dcdfe6;
        border-radius: 5px;
        padding: 7px 10px;
        color: #2c3e50;
        selection-background-color: #1abc9c;
    }

    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus, QTimeEdit:focus {
        border-color: #1abc9c;
        outline: none;
    }

    QLabel {
        color: #2c3e50;
    }

    QGroupBox {
        border: 1px solid #e8ecef;
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 16px;
        background-color: #ffffff;
        font-weight: bold;
        color: #2c3e50;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        left: 16px;
        padding: 0 8px;
    }

    QTabWidget::pane {
        border: 1px solid #e8ecef;
        border-radius: 8px;
        top: -1px;
        background: #ffffff;
    }

    QTabBar::tab {
        background: #f5f7fa;
        border: 1px solid #e8ecef;
        border-bottom: none;
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        margin-right: 4px;
        color: #7f8c8d;
    }

    QTabBar::tab:selected {
        background: #ffffff;
        color: #1abc9c;
        font-weight: bold;
    }

    QTabBar::tab:hover {
        color: #1abc9c;
    }

    QListWidget {
        background-color: #ffffff;
        border: 1px solid #e8ecef;
        border-radius: 8px;
        padding: 4px;
        outline: none;
    }

    QListWidget::item {
        padding: 10px 12px;
        border-radius: 4px;
        margin: 2px;
    }

    QListWidget::item:hover {
        background-color: #f5f7fa;
    }

    QListWidget::item:selected {
        background-color: #e8f5f2;
        color: #1abc9c;
    }

    QProgressBar {
        border: 1px solid #e8ecef;
        border-radius: 6px;
        text-align: center;
        background-color: #f5f7fa;
        height: 20px;
    }

    QProgressBar::chunk {
        border-radius: 5px;
        background-color: #1abc9c;
    }

    QRadioButton {
        spacing: 6px;
        color: #2c3e50;
    }

    QRadioButton::indicator {
        width: 16px;
        height: 16px;
    }

    QCheckBox {
        spacing: 6px;
        color: #2c3e50;
    }

    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border-radius: 3px;
    }

    QCheckBox::indicator:checked {
        background-color: #1abc9c;
        border: 1px solid #1abc9c;
    }

    QScrollBar:vertical {
        border: none;
        background: #f5f7fa;
        width: 8px;
        border-radius: 4px;
    }

    QScrollBar::handle:vertical {
        background: #bdc3c7;
        border-radius: 4px;
        min-height: 30px;
    }

    QScrollBar::handle:vertical:hover {
        background: #95a5a6;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }

    QScrollBar:horizontal {
        border: none;
        background: #f5f7fa;
        height: 8px;
        border-radius: 4px;
    }

    QScrollBar::handle:horizontal {
        background: #bdc3c7;
        border-radius: 4px;
        min-width: 30px;
    }

    QScrollBar::handle:horizontal:hover {
        background: #95a5a6;
    }

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0;
    }
    """
