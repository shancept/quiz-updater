from __future__ import annotations


class BackendError(Exception):
    """Ошибка бэкенда с машиночитаемым кодом для UI.

    details — дополнительные поля, которые уходят в JSON-ответ рядом с code/error
    (например, clientEmail для FILE_NOT_SHARED, чтобы UI показал кнопку «Скопировать»).
    """

    def __init__(self, code: str, message: str, **details) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
