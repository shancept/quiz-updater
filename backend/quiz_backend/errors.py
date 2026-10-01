from __future__ import annotations


class BackendError(Exception):
    """Ошибка бэкенда с машиночитаемым кодом для UI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
