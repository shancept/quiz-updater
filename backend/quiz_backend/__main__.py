from __future__ import annotations

import argparse
import json
import sys

from . import drive as drive_mod
from . import excel as excel_mod
from . import keynote as keynote_mod
from . import schedule as schedule_mod
from .applescript import run_applescript
from .errors import BackendError

DEFAULT_SLIDE = 81
DEFAULT_MAX_ROWS = 10
DEFAULT_COMPRESSION = 0.5


def parse_pairs(pairs_str: str) -> list:
    """Парсит строку 'место:слайд,место:слайд,...' в список (place, slide)."""
    result = []
    for pair in pairs_str.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if ":" not in pair:
            raise BackendError(
                "INVALID_ARGUMENT",
                f"Неверный формат пары: '{pair}'. Ожидается 'место:слайд', например '1:182'",
            )
        place_str, slide_str = pair.split(":", 1)
        try:
            result.append((int(place_str), int(slide_str)))
        except ValueError as exc:
            raise BackendError("INVALID_ARGUMENT", f"Неверный формат пары: '{pair}'") from exc
    return result


def cmd_list_documents(args: argparse.Namespace) -> dict:
    running = keynote_mod.is_keynote_running()
    documents = keynote_mod.list_documents() if running else []
    return {"keynoteRunning": running, "documents": documents}


def download_teams(file_id: str, rounds: int) -> tuple:
    """Скачивает таблицу с Drive заново (без кэша) и читает команды → (метаданные файла, команды)."""
    meta, data = drive_mod.installed_client().download_xlsx(file_id)
    return meta, excel_mod.read_teams(data, rounds)


def cmd_drive_status(args: argparse.Namespace) -> dict:
    # Без сети: только читает адрес робота из ключа на диске.
    if not drive_mod.is_connected():
        return {"connected": False, "clientEmail": None}
    return {"connected": True, "clientEmail": drive_mod.load_installed_key().client_email}


def cmd_connect_drive(args: argparse.Namespace) -> dict:
    key = drive_mod.read_key_file(args.key)
    sheets = drive_mod.client_for(key).list_sheets()  # токен + запрос = проверка, что ключ рабочий
    drive_mod.install_key(args.key)  # только после успешной проверки: рабочий ключ не затирается
    return {"clientEmail": key.client_email, "sheetCount": len(sheets)}


def cmd_list_sheets(args: argparse.Namespace) -> dict:
    client = drive_mod.installed_client()
    return {"clientEmail": client.client_email, "sheets": client.list_sheets()}


def cmd_resolve_link(args: argparse.Namespace) -> dict:
    file_id = drive_mod.parse_drive_link(args.link)
    return {"sheet": drive_mod.installed_client().get_sheet(file_id)}


def cmd_read_sheet(args: argparse.Namespace) -> dict:
    meta, teams = download_teams(args.file_id, args.rounds)
    return {"sheetName": meta["name"], "teams": teams}


def cmd_export_previews(args: argparse.Namespace) -> dict:
    doc_name = keynote_mod.resolve_doc_name(args.doc)
    slides = keynote_mod.export_slide_images(doc_name, args.out, compression=args.compression)
    return {"doc": doc_name, "slides": slides, "count": len(slides)}


def cmd_update_rating(args: argparse.Namespace) -> dict:
    doc_name = keynote_mod.resolve_doc_name(args.doc)
    # Число раундов задаёт таблица Keynote на выбранном слайде, а не таблица на Drive.
    table = keynote_mod.read_rating_table(doc_name, args.slide)
    _, teams = download_teams(args.file_id, table["rounds"])
    teams = teams[: args.max_rows]
    if not teams:
        raise BackendError(
            "EXCEL_BAD_FORMAT",
            f"В таблице на Drive (лист «{excel_mod.SHEET_NAME}») не найдено ни одной команды: "
            "данные должны идти со 2-й строки, место и название команды — в колонках A и B.",
        )

    # Число строк таблицы Keynote подгоняется под число команд: недостающие добавляются,
    # лишние удаляются (иначе в них остались бы данные прошлой игры).
    rows = keynote_mod.plan_row_change(table["rows"], len(teams), table["height"], table["font_size"])
    rows_info = {
        "keynoteRows": rows["currentRows"],
        "targetRows": rows["targetRows"],
        "rowsAdded": rows["added"],
        "rowsRemoved": rows["removed"],
        "warnings": rows["warnings"],
    }

    if args.dry_run:
        return {"dryRun": True, "doc": doc_name, "slide": args.slide, "rounds": table["rounds"],
                "teams": teams, **rows_info}

    script = keynote_mod.build_rating_script(teams, args.slide, doc_name)
    message = run_applescript(script)
    if rows["currentRows"] != rows["targetRows"]:
        message += f" (строк в таблице: {rows['currentRows']} → {rows['targetRows']})"
    return {
        "dryRun": False,
        "doc": doc_name,
        "slide": args.slide,
        "rounds": table["rounds"],
        "updated": len(teams),
        "message": message,
        **rows_info,
    }


def cmd_replace_names(args: argparse.Namespace) -> dict:
    doc_name = keynote_mod.resolve_doc_name(args.doc)
    _, teams = download_teams(args.file_id, rounds=0)
    by_place = excel_mod.teams_by_place(teams)
    pairs = parse_pairs(args.pairs)

    assignments = []
    warnings = []
    for place, slide_num in pairs:
        if place not in by_place:
            warnings.append(f"Место {place} не найдено в Excel")
            continue
        assignments.append((place, slide_num, by_place[place]))

    if not assignments:
        raise BackendError(
            "EXCEL_BAD_FORMAT",
            "; ".join(warnings) if warnings else "Нет данных для замены",
        )

    if args.dry_run:
        slide_nums = [a[1] for a in assignments]
        found_map = keynote_mod.check_placeholders(doc_name, slide_nums)
        assignment_dicts = [
            {"place": p, "slide": s, "team": t, "placeholderFound": found_map.get(s, False)}
            for p, s, t in assignments
        ]
        return {"dryRun": True, "doc": doc_name, "assignments": assignment_dicts, "warnings": warnings}

    script = keynote_mod.build_names_script(assignments, doc_name)
    message = run_applescript(script)
    assignment_dicts = [{"place": p, "slide": s, "team": t} for p, s, t in assignments]
    return {
        "dryRun": False,
        "doc": doc_name,
        "assignments": assignment_dicts,
        "updated": len(assignments),
        "message": message,
        "warnings": warnings,
    }


def cmd_fetch_schedule(args: argparse.Namespace) -> dict:
    games = schedule_mod.build_schedule()
    return {"games": games}


def cmd_fill_schedule_slots(args: argparse.Namespace) -> dict:
    doc_name = keynote_mod.resolve_doc_name(args.doc)

    try:
        games = json.loads(args.games)
    except json.JSONDecodeError as exc:
        raise BackendError("INVALID_ARGUMENT", f"Некорректный JSON в --games: {exc}") from exc

    warnings = []
    if len(games) > keynote_mod.SCHEDULE_SLOT_COUNT:
        warnings.append(
            f"Игр больше, чем слотов ({len(games)} > {keynote_mod.SCHEDULE_SLOT_COUNT}): "
            f"показаны будут только первые {keynote_mod.SCHEDULE_SLOT_COUNT}."
        )

    text_items = keynote_mod.read_slide_text_items(doc_name, args.slide)
    pairs = keynote_mod.compute_card_pairs(text_items)

    if args.dry_run:
        preview = []
        for pair in pairs:
            game = games[pair["slotIndex"] - 1] if pair["slotIndex"] - 1 < len(games) else None
            preview.append({
                "slotIndex": pair["slotIndex"],
                "filled": game is not None,
                "cardText": game["cardText"] if game else None,
                "dateText": game["dateText"] if game else None,
            })
        return {"dryRun": True, "doc": doc_name, "slide": args.slide, "slots": preview, "warnings": warnings}

    script = keynote_mod.build_fill_text_slots_script(doc_name, args.slide, pairs, games)
    message = run_applescript(script)
    filled = min(len(games), len(pairs))
    return {
        "dryRun": False,
        "doc": doc_name,
        "slide": args.slide,
        "filledCount": filled,
        "clearedCount": len(pairs) - filled,
        "message": message,
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quiz_backend")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_list = subparsers.add_parser("list-documents")
    p_list.set_defaults(handler=cmd_list_documents)

    p_status = subparsers.add_parser("drive-status")
    p_status.set_defaults(handler=cmd_drive_status)

    p_connect = subparsers.add_parser("connect-drive")
    p_connect.add_argument("--key", type=str, required=True, help="путь к JSON-ключу сервисного аккаунта")
    p_connect.set_defaults(handler=cmd_connect_drive)

    p_sheets = subparsers.add_parser("list-sheets")
    p_sheets.set_defaults(handler=cmd_list_sheets)

    p_link = subparsers.add_parser("resolve-link")
    p_link.add_argument("--link", type=str, required=True, help="ссылка на таблицу в Google Drive / Sheets")
    p_link.set_defaults(handler=cmd_resolve_link)

    p_read = subparsers.add_parser("read-sheet")
    p_read.add_argument("--file-id", type=str, required=True, dest="file_id")
    p_read.add_argument("--rounds", type=int, default=0, help="сколько колонок раундов (с D) прочитать")
    p_read.set_defaults(handler=cmd_read_sheet)

    p_export = subparsers.add_parser("export-previews")
    p_export.add_argument("--doc", type=str, default=None)
    p_export.add_argument("--out", type=str, required=True)
    p_export.add_argument("--compression", type=float, default=DEFAULT_COMPRESSION)
    p_export.set_defaults(handler=cmd_export_previews)

    p_rating = subparsers.add_parser("update-rating")
    p_rating.add_argument("--doc", type=str, default=None)
    p_rating.add_argument("--slide", type=int, default=DEFAULT_SLIDE)
    p_rating.add_argument("--file-id", type=str, required=True, dest="file_id")
    p_rating.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS, dest="max_rows")
    p_rating.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_rating.set_defaults(handler=cmd_update_rating)

    p_names = subparsers.add_parser("replace-names")
    p_names.add_argument("--doc", type=str, default=None)
    p_names.add_argument("--file-id", type=str, required=True, dest="file_id")
    p_names.add_argument("--pairs", type=str, required=True, help="место:слайд,место:слайд, например 1:182,2:181")
    p_names.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_names.set_defaults(handler=cmd_replace_names)

    p_fetch_schedule = subparsers.add_parser("fetch-schedule")
    p_fetch_schedule.set_defaults(handler=cmd_fetch_schedule)

    p_fill_slots = subparsers.add_parser("fill-schedule-slots")
    p_fill_slots.add_argument("--doc", type=str, default=None)
    p_fill_slots.add_argument("--slide", type=int, required=True)
    p_fill_slots.add_argument("--games", type=str, required=True, help="JSON-массив [{cardText,dateText}]")
    p_fill_slots.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_fill_slots.set_defaults(handler=cmd_fill_schedule_slots)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        payload = args.handler(args)
        print(json.dumps({"ok": True, **payload}, ensure_ascii=False))
        return 0
    except BackendError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "error": exc.message, **exc.details}, ensure_ascii=False))
        return 1
    except Exception as exc:  # noqa: BLE001 - всегда возвращаем валидный JSON наверх
        print(json.dumps({"ok": False, "code": "UNKNOWN_ERROR", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
