#!/usr/bin/env python3
"""
Автоматизация обновления таблицы рейтинга в Keynote из Excel.

Читает данные из Excel-файла (Лист1) и обновляет таблицу
на указанном слайде в открытой презентации Keynote.

Использование:
    python3 update_keynote_rating.py [--slide НОМЕР] [--excel ПУТЬ] [--keynote ИМЯ] [--max-rows N]

Примеры:
    # Обновить слайд 81 (по умолчанию)
    python3 update_keynote_rating.py

    # Указать другой слайд
    python3 update_keynote_rating.py --slide 85

    # Указать все параметры
    python3 update_keynote_rating.py --slide 81 --max-rows 10
"""

import argparse
import subprocess
import sys
import os

import openpyxl


# Пути по умолчанию
DEFAULT_EXCEL = os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-shancept@gmail.com/"
    "My Drive/КВИЗ/Копия Копия Калькулятор баллов Классика.xlsx"
)
DEFAULT_SLIDE = 81
DEFAULT_MAX_ROWS = 10


def read_excel(path: str) -> list[dict]:
    """Читает таблицу рейтинга из Excel и возвращает список команд."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Лист1"]

    teams = []
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


def format_value(val) -> str:
    """Форматирует значение для AppleScript."""
    if val is None:
        return '""'
    if isinstance(val, float):
        if val == int(val):
            return str(int(val))
        return str(val)
    if isinstance(val, int):
        return str(val)
    # Строка — экранируем кавычки
    escaped = str(val).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_applescript(teams: list[dict], slide_num: int, keynote_doc: str | None) -> str:
    """Генерирует AppleScript для обновления таблицы в Keynote."""

    # Формируем команды для каждой ячейки
    set_commands = []
    for i, team in enumerate(teams):
        row = i + 1  # Keynote row (1-based, no header in data table)

        # Колонка 1: МЕСТО
        set_commands.append(
            f'set value of cell 1 of row {row} of t to {format_value(team["place"])}'
        )
        # Колонка 2: КОМАНДА
        set_commands.append(
            f'set value of cell 2 of row {row} of t to {format_value(team["name"])}'
        )
        # Колонка 3: ИТОГО
        set_commands.append(
            f'set value of cell 3 of row {row} of t to {format_value(team["total"])}'
        )
        # Колонки 4-10: РАУНД 1-7
        for j, rv in enumerate(team["rounds"]):
            col = j + 4
            set_commands.append(
                f'set value of cell {col} of row {row} of t to {format_value(rv)}'
            )

    sets_block = "\n            ".join(set_commands)

    # Определяем, как обращаться к документу
    if keynote_doc:
        doc_ref = f'document "{keynote_doc}"'
    else:
        doc_ref = "front document"

    script = f"""
tell application "Keynote"
    tell {doc_ref}
        set s to slide {slide_num}
        -- Таблица 1 = таблица с данными (без заголовка)
        set t to table 1 of s
        set rowCount to count of rows of t

        if rowCount < {len(teams)} then
            error "В таблице Keynote только " & rowCount & " строк, а данных {len(teams)}"
        end if

        {sets_block}
    end tell
end tell
return "OK: обновлено {len(teams)} команд на слайде {slide_num}"
"""
    return script


def run_applescript(script: str) -> str:
    """Выполняет AppleScript и возвращает результат."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript error:\n{result.stderr.strip()}")
    return result.stdout.strip()


def get_open_keynote_doc() -> str | None:
    """Возвращает имя первого открытого документа Keynote или None."""
    try:
        result = subprocess.run(
            ["osascript", "-e", 'tell application "Keynote" to return name of front document'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Обновление таблицы рейтинга в Keynote из Excel"
    )
    parser.add_argument(
        "--slide", type=int, default=DEFAULT_SLIDE,
        help=f"Номер слайда с таблицей (по умолчанию: {DEFAULT_SLIDE})"
    )
    parser.add_argument(
        "--excel", type=str, default=DEFAULT_EXCEL,
        help="Путь к Excel-файлу"
    )
    parser.add_argument(
        "--keynote", type=str, default=None,
        help="Имя документа Keynote (по умолчанию: активный документ)"
    )
    parser.add_argument(
        "--max-rows", type=int, default=DEFAULT_MAX_ROWS,
        help=f"Максимум строк для обновления (по умолчанию: {DEFAULT_MAX_ROWS})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Показать данные без обновления Keynote"
    )

    args = parser.parse_args()

    # 1. Читаем Excel
    print(f"📊 Чтение Excel: {os.path.basename(args.excel)}")
    if not os.path.exists(args.excel):
        print(f"❌ Файл не найден: {args.excel}", file=sys.stderr)
        sys.exit(1)

    teams = read_excel(args.excel)
    print(f"   Найдено команд: {len(teams)}")

    # Ограничиваем количество
    teams = teams[:args.max_rows]
    print(f"   Будет обновлено: {len(teams)}")

    # Показываем превью
    print()
    print(f"{'№':<4} {'Команда':<30} {'Итого':<8} " + " ".join(f"{'Р' + str(i+1):<6}" for i in range(7)))
    print("-" * 90)
    for t in teams:
        rounds_str = " ".join(f"{(r if r is not None else '-'):<6}" for r in t["rounds"])
        print(f"{t['place']:<4} {t['name']:<30} {t['total']:<8} {rounds_str}")
    print()

    if args.dry_run:
        print("🔍 Dry run — Keynote не обновлён")
        return

    # 2. Определяем документ Keynote
    keynote_doc = args.keynote
    if not keynote_doc:
        keynote_doc = get_open_keynote_doc()
        if not keynote_doc:
            print("❌ Нет открытого документа Keynote", file=sys.stderr)
            sys.exit(1)
    print(f"🎯 Keynote: {keynote_doc}, слайд {args.slide}")

    # 3. Генерируем и выполняем AppleScript
    script = build_applescript(teams, args.slide, keynote_doc)
    print("⏳ Обновление таблицы...")

    try:
        result = run_applescript(script)
        print(f"✅ {result}")
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
