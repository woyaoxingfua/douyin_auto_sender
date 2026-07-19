import logging
from PySide6.QtCore import QObject, Signal


class QtLogHandler(logging.Handler, QObject):
    log_message = Signal(str, str)

    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_message.emit(record.levelname, msg)
        except Exception:
            self.handleError(record)
