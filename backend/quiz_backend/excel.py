from __future__ import annotations

import os

import openpyxl

from .errors import BackendError

SHEET_NAME = "Лист1"


def read_teams(path: str) -> list[dict]:
    """Читает таблицу рейтинга из Excel и возвращает список команд.

    Каждая запись: {"place": int|str, "name": str, "total": Any, "rounds": [7 значений]}.
    Данные читаются со 2-й строки листа SHEET_NAME до первой пустой строки.
    """
    if not os.path.exists(path):
        raise BackendError("EXCEL_NOT_FOUND", f"Файл не найден: {path}")

    try:
        wb = openpyxl.load_workbook(path, data_only=True)
    except Exception as exc:
        raise BackendError("EXCEL_BAD_FORMAT", f"Не удалось открыть Excel-файл: {exc}") from exc

    if SHEET_NAME not in wb.sheetnames:
        wb.close()
        raise BackendError(
            "EXCEL_BAD_FORMAT",
            f"Лист '{SHEET_NAME}' не найден. Доступные листы: {', '.join(wb.sheetnames)}",
        )

    ws = wb[SHEET_NAME]

    teams: list[dict] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        place = row[0]  # A: место
        name = row[1]   # B: команда
        total = row[2]  # C: итого
        rounds = list(row[3:10])  # D-J: раунды 1-7

        if place is None or name is None:
            break

        teams.append({
            "place": int(place) if isinstance(place, float) and place == int(place) else place,
            "name": str(name),
            "total": total,
            "rounds": rounds,
        })

    wb.close()
    return teams


def teams_by_place(teams: list[dict]) -> dict[int, str]:
    """Строит словарь {место: имя команды} из результата read_teams()."""
    result: dict[int, str] = {}
    for team in teams:
        place = team["place"]
        place_int = int(place)
        result[place_int] = team["name"]
    return result
