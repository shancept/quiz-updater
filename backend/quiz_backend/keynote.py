from __future__ import annotations

import glob
import os
import re

from .applescript import escape_as_string, format_multiline_value, format_value, run_applescript
from .errors import BackendError

PLACEHOLDER = "ЗАМЕНИТЬ"
SCHEDULE_SLOT_COUNT = 4


def is_keynote_running() -> bool:
    result = run_applescript('application "Keynote" is running')
    return result.strip().lower() == "true"


def list_documents() -> list[dict]:
    """Возвращает [{"name": str, "slideCount": int}, ...] для открытых документов Keynote."""
    if not is_keynote_running():
        return []

    script = """
tell application "Keynote"
    set output to ""
    repeat with d in documents
        set output to output & (name of d) & tab & (count of slides of d) & linefeed
    end repeat
    return output
end tell
"""
    result = run_applescript(script)
    documents: list[dict] = []
    for line in result.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        name, slide_count = parts
        documents.append({"name": name, "slideCount": int(slide_count)})
    return documents


def get_front_document_name() -> str | None:
    """Возвращает имя переднего документа Keynote или None, если нет открытых документов."""
    if not is_keynote_running():
        return None
    result = run_applescript('tell application "Keynote" to return name of front document')
    return result if result else None


def resolve_doc_name(doc_name: str | None) -> str:
    """Проверяет/определяет имя документа Keynote и поднимает BackendError при проблемах."""
    if not is_keynote_running():
        raise BackendError("KEYNOTE_NOT_RUNNING", "Keynote не запущен")

    if doc_name:
        documents = list_documents()
        if not any(d["name"] == doc_name for d in documents):
            raise BackendError("DOC_NOT_FOUND", f"Документ не найден среди открытых: {doc_name}")
        return doc_name

    name = get_front_document_name()
    if not name:
        raise BackendError("DOC_NOT_FOUND", "Нет открытого документа Keynote")
    return name


def _doc_ref(doc_name: str) -> str:
    return f'document "{escape_as_string(doc_name)}"'


def export_slide_images(doc_name: str, out_dir: str, compression: float = 0.5) -> list[dict]:
    """Экспортирует все слайды документа как JPEG в out_dir (Keynote сам создаёт папку).

    Возвращает [{"slide": int, "path": str}, ...] в порядке номеров слайдов.
    skipped slides:true обязателен, чтобы нумерация экспортированных файлов совпадала
    с AppleScript-индексом слайда (`slide N`), даже если в презентации есть пропущенные слайды.
    """
    # Keynote сам создаёт последний компонент пути (out_dir), но родительская
    # папка должна существовать заранее.
    parent_dir = os.path.dirname(out_dir.rstrip("/")) or "/"
    os.makedirs(parent_dir, exist_ok=True)

    doc_ref = _doc_ref(doc_name)
    escaped_path = escape_as_string(out_dir)

    script = f"""
tell application "Keynote"
    export {doc_ref} to POSIX file "{escaped_path}" as slide images ¬
        with properties {{image format:JPEG, compression factor:{compression}, skipped slides:true, all stages:false}}
end tell
return "OK"
"""
    run_applescript(script, timeout=300)

    files = glob.glob(os.path.join(out_dir, "*.jpeg"))
    if not files:
        raise BackendError("APPLESCRIPT_ERROR", "Keynote не создал файлы превью слайдов")

    def slide_number(path: str) -> int:
        match = re.search(r"\.(\d+)\.jpeg$", path)
        if not match:
            return 0
        return int(match.group(1))

    files.sort(key=slide_number)
    return [{"slide": i + 1, "path": path} for i, path in enumerate(files)]


def build_rating_script(teams: list[dict], slide_num: int, doc_name: str) -> str:
    """Генерирует AppleScript для обновления таблицы рейтинга на слайде."""
    set_commands = []
    for i, team in enumerate(teams):
        row = i + 1  # Keynote row (1-based, без заголовка)

        set_commands.append(f'set value of cell 1 of row {row} of t to {format_value(team["place"])}')
        set_commands.append(f'set value of cell 2 of row {row} of t to {format_value(team["name"])}')
        set_commands.append(f'set value of cell 3 of row {row} of t to {format_value(team["total"])}')
        for j, rv in enumerate(team["rounds"]):
            col = j + 4
            set_commands.append(f'set value of cell {col} of row {row} of t to {format_value(rv)}')

    sets_block = "\n            ".join(set_commands)
    doc_ref = _doc_ref(doc_name)

    return f"""
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


def build_names_script(assignments: list[tuple], doc_name: str) -> str:
    """Генерирует AppleScript для замены плейсхолдера ЗАМЕНИТЬ именами команд.

    assignments: список (place, slide_num, team_name).
    """
    doc_ref = _doc_ref(doc_name)

    replace_blocks = []
    for place, slide_num, team_name in assignments:
        escaped_name = escape_as_string(team_name)
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

    return f"""
tell application "Keynote"
    tell {doc_ref}
{blocks}
    end tell
end tell
return "OK: обновлено {len(assignments)} слайдов"
"""


def check_placeholders(doc_name: str, slide_nums: list[int]) -> dict[int, bool]:
    """Read-only проверка наличия текста ЗАМЕНИТЬ на каждом из указанных слайдов."""
    doc_ref = _doc_ref(doc_name)
    slide_list = ", ".join(str(n) for n in slide_nums)

    script = f"""
tell application "Keynote"
    tell {doc_ref}
        set output to ""
        repeat with slideNum in {{{slide_list}}}
            set s to slide slideNum
            set found to false
            repeat with ti in text items of s
                if object text of ti is "{PLACEHOLDER}" then
                    set found to true
                    exit repeat
                end if
            end repeat
            set output to output & slideNum & tab & found & linefeed
        end repeat
        return output
    end tell
end tell
"""
    result = run_applescript(script)
    found_map: dict[int, bool] = {}
    for line in result.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        slide_num, found = parts
        found_map[int(slide_num)] = found.strip().lower() == "true"
    return found_map


def read_slide_text_items(doc_name: str, slide_num: int) -> list[dict]:
    """Read-only: все текстовые элементы слайда с индексом, позицией, размером и текстом.

    Возвращает [{"index","x","y","width","height","text"}, ...].
    Без группировки — просто все text items слайда как есть (декоративные заголовки
    и неиспользуемые layout-плейсхолдеры отфильтровываются потом в compute_card_pairs).
    """
    doc_ref = _doc_ref(doc_name)

    script = f"""
tell application "Keynote"
    tell {doc_ref}
        set s to slide {slide_num}
        set output to ""
        set n to count of text items of s
        repeat with i from 1 to n
            set ti to text item i of s
            set p to position of ti
            set output to output & i & tab & (item 1 of p) & tab & (item 2 of p) & tab & (width of ti) & tab & (height of ti) & tab & (object text of ti) & linefeed
        end repeat
        return output
    end tell
end tell
"""
    result = run_applescript(script)
    items: list[dict] = []
    for line in result.split("\n"):
        line = line.rstrip("\r")
        if not line:
            continue
        parts = line.split("\t", 5)
        if len(parts) != 6:
            continue
        index, x, y, width, height, text = parts
        items.append({
            "index": int(index), "x": float(x), "y": float(y),
            "width": float(width), "height": float(height), "text": text,
        })
    return items


# Допуск по Y (в points) для отнесения двух текстовых полей к одной "строке-карточке".
# Keynote может слегка сдвигать/растягивать рамку поля при автоподгонке под контент даже
# после принудительного восстановления позиции/размера — допуск должен быть заметно больше
# такого дрейфа (наблюдалось до ~70pt для одного поля), но заметно меньше расстояния между
# соседними строками карточек на слайде (обычно 200+pt).
ROW_Y_TOLERANCE = 80.0
# Текстовые элементы точно в начале координат — неиспользуемые layout-плейсхолдеры слайда
# (не карточки), исключаются из рассмотрения независимо от текста.
ORIGIN_EPSILON = 1.0


def compute_card_pairs(text_items: list[dict], expected_count: int = SCHEDULE_SLOT_COUNT) -> list[dict]:
    """Чистая Python-функция без AppleScript: находит пары текстовых полей "тема слева / дата
    справа" среди ВСЕХ текстовых элементов слайда — без какой-либо группировки в Keynote.

    Правило: текстовые поля НЕ в начале координат (0,0) группируются по Y (с допуском
    ROW_Y_TOLERANCE) — это "строки". ВАЖНО: текст НЕ учитывается при фильтрации — уже
    очищенный (пустой) слот от предыдущего запуска должен находиться снова, иначе он
    "потеряется" навсегда. Только позиция (0,0) отсеивает неиспользуемые layout-элементы.
    Строка с НЕЧЁТНЫМ числом полей считается декоративной (заголовок/подзаголовок/подпись —
    их всегда одна штука в строке) и отбрасывается. Строка с ЧЁТНЫМ числом полей разбивается
    на пары по возрастанию X (первые два - одна карточка, следующие два - следующая и т.д.).
    Все пары сортируются по (Y, X) - это и есть порядок слотов 1..N.

    Возвращает [{"slotIndex","leftIndex","rightIndex",
                 "leftX","leftY","leftWidth","leftHeight",
                 "rightX","rightY","rightWidth","rightHeight"}, ...] — координаты нужны, чтобы
    после записи текста "закрепить" поле на месте (Keynote может сдвинуть/увеличить рамку
    при смене текста/размера шрифта — иначе на следующий запуск сопоставление пар развалится).
    Поднимает BackendError('TEMPLATE_INVALID', ...), если пар не ровно expected_count.
    """
    candidates = [t for t in text_items if abs(t["x"]) > ORIGIN_EPSILON or abs(t["y"]) > ORIGIN_EPSILON]

    rows: list[list[dict]] = []
    for item in sorted(candidates, key=lambda t: t["y"]):
        for row in rows:
            if abs(row[0]["y"] - item["y"]) <= ROW_Y_TOLERANCE:
                row.append(item)
                break
        else:
            rows.append([item])

    pairs = []
    for row in rows:
        if len(row) % 2 != 0:
            continue
        ordered = sorted(row, key=lambda t: t["x"])
        avg_y = sum(t["y"] for t in ordered) / len(ordered)
        for i in range(0, len(ordered), 2):
            left, right = ordered[i], ordered[i + 1]
            pairs.append({"y": avg_y, "x": left["x"], "left": left, "right": right})

    pairs.sort(key=lambda p: (p["y"], p["x"]))

    if len(pairs) != expected_count:
        raise BackendError(
            "TEMPLATE_INVALID",
            f"На слайде должно быть {expected_count} пар текстовых полей (тема+номер слева, "
            f"дата справа, на одной высоте друг с другом), а найдено {len(pairs)}. "
            "Проверьте выбранный слайд.",
        )

    return [
        {
            "slotIndex": i + 1,
            "leftIndex": p["left"]["index"], "leftX": p["left"]["x"], "leftY": p["left"]["y"],
            "leftWidth": p["left"]["width"], "leftHeight": p["left"]["height"],
            "rightIndex": p["right"]["index"], "rightX": p["right"]["x"], "rightY": p["right"]["y"],
            "rightWidth": p["right"]["width"], "rightHeight": p["right"]["height"],
        }
        for i, p in enumerate(pairs)
    ]


DEFAULT_CARD_FONT_SIZE = 52.0  # базовый размер поля "тема+номер" в шаблоне (см. schedule.BASE_CARD_FONT_SIZE)


def build_fill_text_slots_script(doc_name: str, slide_num: int, pairs: list[dict], games: list[dict]) -> str:
    """Генерирует AppleScript: заполняет текстом первые len(games) пар, очищает (пустая строка)
    остальные. Фон/декорации карточек не трогаются вообще (opacity/группы не используются).
    Размер шрифта левого поля (тема+номер) выставляется по game['cardFontSize'] — иначе
    длинная тема вылезает за рамку карточки; для очищенных слотов сбрасывается на базовый.

    После смены текста/размера шрифта Keynote может сам сдвинуть/увеличить рамку поля
    (авто-подгонка под содержимое) — поэтому после записи позиция/ширина/высота ПРИНУДИТЕЛЬНО
    возвращаются к значениям, прочитанным перед этим (см. read_slide_text_items/compute_card_pairs),
    иначе на следующий запуск сопоставление пар по позиции разъедется."""
    doc_ref = _doc_ref(doc_name)

    blocks = []
    for pair in pairs:
        slot_index = pair["slotIndex"]
        game = games[slot_index - 1] if slot_index - 1 < len(games) else None

        if game is not None:
            card_value = format_multiline_value(str(game["cardText"]))
            date_value = format_value(game["dateText"])
            font_size = game.get("cardFontSize", DEFAULT_CARD_FONT_SIZE)
        else:
            card_value = '""'
            date_value = '""'
            font_size = DEFAULT_CARD_FONT_SIZE

        blocks.append(f"""
        -- Слот {slot_index}
        set object text of text item {pair["leftIndex"]} of s to {card_value}
        set size of object text of text item {pair["leftIndex"]} of s to {font_size}
        set position of text item {pair["leftIndex"]} of s to {{{pair["leftX"]}, {pair["leftY"]}}}
        set width of text item {pair["leftIndex"]} of s to {pair["leftWidth"]}
        set height of text item {pair["leftIndex"]} of s to {pair["leftHeight"]}
        set object text of text item {pair["rightIndex"]} of s to {date_value}
        set position of text item {pair["rightIndex"]} of s to {{{pair["rightX"]}, {pair["rightY"]}}}
        set width of text item {pair["rightIndex"]} of s to {pair["rightWidth"]}
        set height of text item {pair["rightIndex"]} of s to {pair["rightHeight"]}""")

    blocks_text = "\n".join(blocks)
    filled = min(len(games), len(pairs))
    cleared = len(pairs) - filled

    return f"""
tell application "Keynote"
    tell {doc_ref}
        set s to slide {slide_num}
{blocks_text}
    end tell
end tell
return "OK: заполнено слотов — {filled}, очищено — {cleared}"
"""
