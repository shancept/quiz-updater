from __future__ import annotations

import subprocess

from .errors import BackendError


def escape_as_string(value: str) -> str:
    """Экранирует обратные слэши и кавычки для вставки строки в AppleScript."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def format_value(val) -> str:
    """Форматирует значение Python для использования в AppleScript-выражении."""
    if val is None:
        return '""'
    if isinstance(val, float):
        if val == int(val):
            return str(int(val))
        return str(val)
    if isinstance(val, int):
        return str(val)
    return f'"{escape_as_string(str(val))}"'


def format_multiline_value(text: str) -> str:
    """Форматирует многострочный текст как конкатенацию AppleScript-строк через 'return'
    (буквальный '\\n' в AppleScript-литерале строкой не является — только именованные константы)."""
    lines = text.split("\n")
    return " & return & ".join(f'"{escape_as_string(line)}"' for line in lines)


def run_applescript(script: str, timeout: int = 60) -> str:
    """Выполняет AppleScript через osascript и возвращает stdout.

    Поднимает BackendError с кодом AUTOMATION_DENIED, если пользователь
    не разрешил приложению управлять Keynote (TCC), иначе APPLESCRIPT_ERROR.
    """
    try:
        # capture_output в бинарном режиме (без text=True) — иначе Python в текстовом режиме
        # подпроцесса транслирует одиночные '\r' (разделитель абзацев внутри object text,
        # AppleScript-константа 'return') в '\n', что ломает построчный tab/linefeed-парсинг
        # многострочных значений (например, cardText с переносом строки в schedule.py).
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise BackendError("APPLESCRIPT_ERROR", f"Превышено время ожидания AppleScript: {exc}") from exc

    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")

    if result.returncode != 0:
        stderr = stderr.strip()
        if "-1743" in stderr or "Not authorized" in stderr or "not allowed" in stderr.lower():
            raise BackendError(
                "AUTOMATION_DENIED",
                "Нет разрешения на управление Keynote. Разрешите доступ в Настройки → "
                "Конфиденциальность и безопасность → Автоматизация.",
            )
        raise BackendError("APPLESCRIPT_ERROR", f"Ошибка AppleScript: {stderr}")

    return stdout.strip()
