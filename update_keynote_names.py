#!/usr/bin/env python3
"""
Замена текста "ЗАМЕНИТЬ" на слайдах Keynote именами команд из Excel.

Использование:
    # Автоматический расчёт слайдов (1→182, 2→181, 3→180, 8→179)
    python3 update_keynote_names.py --start-slide 182 --places 1 2 3 8

    # Ручное задание пар место-слайд
    python3 update_keynote_names.py --pairs 1-182 2-181 3-180 8-179

    # Превью без обновления
    python3 update_keynote_names.py --start-slide 182 --places 1 2 3 8 --dry-run
"""

import argparse
import subprocess
import sys
import os

import openpyxl


DEFAULT_EXCEL = os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-shancept@gmail.com/"
    "My Drive/КВИЗ/Копия Копия Калькулятор баллов Классика.xlsx"
)
PLACEHOLDER = "ЗАМЕНИТЬ"


def read_excel(path: str) -> dict[int, str]:
    """Читает Excel и возвращает словарь {место: имя_команды}."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Лист1"]

    teams = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        place = row[0]
        name = row[1]
        if place is None or name is None:
            break
        place_int = int(place) if isinstance(place, float) and place == int(place) else int(place)
        teams[place_int] = str(name)

    wb.close()
    return teams


def parse_pairs(pairs: list[str]) -> list[tuple[int, int]]:
    """Парсит пары 'место-слайд' вида '1-182'."""
    result = []
    for pair in pairs:
        parts = pair.split("-")
        if len(parts) != 2:
            raise ValueError(f"Неверный формат пары: '{pair}'. Ожидается 'место-слайд', например '1-182'")
        place, slide = int(parts[0]), int(parts[1])
        result.append((place, slide))
    return result


def calc_slides(start_slide: int, places: list[int]) -> list[tuple[int, int]]:
    """Вычисляет пары (место, слайд) по начальному слайду и списку мест."""
    return [(place, start_slide - i) for i, place in enumerate(places)]


def build_applescript(assignments: list[tuple[int, int, str]], keynote_doc: str | None) -> str:
    """Генерирует AppleScript для замены текста на слайдах."""

    if keynote_doc:
        doc_ref = f'document "{keynote_doc}"'
    else:
        doc_ref = "front document"

    replace_blocks = []
    for place, slide_num, team_name in assignments:
        escaped_name = team_name.replace("\\", "\\\\").replace('"', '\\"')
        replace_blocks.append(f"""
        -- Место {place} → слайд {slide_num}
        set s to slide {slide_num}
        set found to false
        repeat with ti in text items of s
            if object text of ti is "{PLACEHOLDER}" then
                set object text of ti to "{escaped_name}"
                set found to true
                exit repeat
            end if
        end repeat
        if not found then
            error "Не найден текст \\"{PLACEHOLDER}\\" на слайде {slide_num} (место {place})"
        end if""")

    blocks = "\n".join(replace_blocks)

    script = f"""
tell application "Keynote"
    tell {doc_ref}
{blocks}
    end tell
end tell
return "OK: обновлено {len(assignments)} слайдов"
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
        description="Замена текста 'ЗАМЕНИТЬ' на слайдах Keynote именами команд из Excel"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--pairs", nargs="+", metavar="МЕСТО-СЛАЙД",
        help="Пары место-слайд, например: 1-182 2-181 3-180 8-179"
    )
    group.add_argument(
        "--start-slide", type=int, metavar="НОМЕР",
        help="Начальный слайд (для 1-го места в списке --places)"
    )

    parser.add_argument(
        "--places", nargs="+", type=int, metavar="N",
        help="Список мест для замены, например: 1 2 3 8 (обязателен с --start-slide)"
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
        "--dry-run", action="store_true",
        help="Показать план замен без обновления Keynote"
    )

    args = parser.parse_args()

    # Валидация аргументов
    if args.start_slide is not None and not args.places:
        parser.error("--places обязателен при использовании --start-slide")

    # Определяем пары место→слайд
    if args.pairs:
        place_slide_pairs = parse_pairs(args.pairs)
    else:
        place_slide_pairs = calc_slides(args.start_slide, args.places)

    # Читаем Excel
    print(f"📊 Чтение Excel: {os.path.basename(args.excel)}")
    if not os.path.exists(args.excel):
        print(f"❌ Файл не найден: {args.excel}", file=sys.stderr)
        sys.exit(1)

    teams = read_excel(args.excel)
    print(f"   Найдено команд: {len(teams)}")

    # Формируем задания на замену
    assignments = []
    errors = []
    for place, slide_num in place_slide_pairs:
        if place not in teams:
            errors.append(f"Место {place} не найдено в Excel")
        else:
            assignments.append((place, slide_num, teams[place]))

    if errors:
        for err in errors:
            print(f"⚠️  {err}", file=sys.stderr)
        if not assignments:
            print("❌ Нет данных для замены", file=sys.stderr)
            sys.exit(1)

    # Превью
    print()
    print(f"{'Место':<8} {'Слайд':<8} {'Команда'}")
    print("-" * 50)
    for place, slide_num, team_name in assignments:
        print(f"{place:<8} {slide_num:<8} {team_name}")
    print()

    if args.dry_run:
        print("🔍 Dry run — Keynote не обновлён")
        return

    # Определяем документ Keynote
    keynote_doc = args.keynote
    if not keynote_doc:
        keynote_doc = get_open_keynote_doc()
        if not keynote_doc:
            print("❌ Нет открытого документа Keynote", file=sys.stderr)
            sys.exit(1)
    print(f"🎯 Keynote: {keynote_doc}")

    # Генерируем и выполняем AppleScript
    script = build_applescript(assignments, keynote_doc)
    print("⏳ Замена текста на слайдах...")

    try:
        result = run_applescript(script)
        print(f"✅ {result}")
    except RuntimeError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
