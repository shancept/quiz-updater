from __future__ import annotations

import datetime
import json
import urllib.error
import urllib.request

from .errors import BackendError

CITY_ID = 187  # id города София в сервисе api.quizplease.com
API_URL = "https://api.quizplease.com/api/games/schedule/{city_id}"
REQUEST_TIMEOUT = 15

MONTHS_GENITIVE = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def fetch_games(city_id: int = CITY_ID, per_page: int = 100) -> list[dict]:
    """Загружает все игры расписания (с обходом пагинации) через urllib.request."""
    games: list[dict] = []
    page = 1
    total_pages = 1

    while page <= total_pages:
        query = (
            f"per_page={per_page}&order=date&page={page}"
            "&statuses[]=0&statuses[]=1&statuses[]=2&statuses[]=3&statuses[]=5"
        )
        url = f"{API_URL.format(city_id=city_id)}?{query}"
        try:
            with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as response:
                if response.getcode() != 200:
                    raise BackendError(
                        "SCHEDULE_FETCH_ERROR", f"Сервер расписания вернул код {response.getcode()}"
                    )
                body = response.read()
        except urllib.error.URLError as exc:
            raise BackendError(
                "SCHEDULE_FETCH_ERROR", f"Не удалось загрузить расписание игр: {exc}"
            ) from exc
        except TimeoutError as exc:
            raise BackendError(
                "SCHEDULE_FETCH_ERROR", "Превышено время ожидания ответа от сайта расписания"
            ) from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise BackendError(
                "SCHEDULE_FETCH_ERROR", f"Некорректный ответ сервера расписания: {exc}"
            ) from exc

        data = payload.get("data", {})
        games.extend(data.get("data", []))
        pagination = data.get("pagination", {})
        total_pages = pagination.get("total_pages", 1) or 1
        page += 1

    return games


def format_date_text(date_str: str) -> str:
    """'21.07.2026 20:00' -> '21 ИЮЛЯ' (без года, времени, дня недели, ЗАГЛАВНЫМИ)."""
    date_part = date_str.split(" ")[0]
    day_str, month_str, _year_str = date_part.split(".")
    day = int(day_str)
    month = int(month_str)
    return f"{day} {MONTHS_GENITIVE[month]}".upper()


def parse_game_date(date_str: str) -> datetime.date:
    date_part = date_str.split(" ")[0]
    day_str, month_str, year_str = date_part.split(".")
    return datetime.date(int(year_str), int(month_str), int(day_str))


def format_card_text(title: str, game_number: str) -> str:
    """Классика -> '#NN'; тематическая (title начинается с '[') -> 'ТЕМА\nномер'. Всё ЗАГЛАВНЫМИ."""
    if title.startswith("["):
        theme = title.replace("SOFIA", "").strip()
        return f"{theme}\n#{game_number}".upper()
    return f"#{game_number}".upper()


BASE_CARD_FONT_SIZE = 52.0
MIN_CARD_FONT_SIZE = 16.0
SAFE_LINE_LENGTH = 10  # длина строки, которая ещё умещается в поле карточки при базовом размере


def compute_card_font_size(card_text: str) -> float:
    """Подбирает размер шрифта для поля 'тема+номер': короткий текст (классика, '#NN') —
    базовый размер поля-шаблона; длинная строка темы — пропорционально меньше, чтобы не
    вылезать за рамку карточки (у Keynote-текста при этом growbox иначе съезжает по позиции)."""
    longest_line = max((len(line) for line in card_text.split("\n")), default=0)
    if longest_line <= SAFE_LINE_LENGTH:
        return BASE_CARD_FONT_SIZE
    scaled = BASE_CARD_FONT_SIZE * (SAFE_LINE_LENGTH / longest_line)
    return max(MIN_CARD_FONT_SIZE, round(scaled))


def build_schedule() -> list[dict]:
    """Загружает и готовит список предстоящих игр: без сегодняшних/прошедших, отсортировано по дате."""
    raw_games = fetch_games()
    today = datetime.date.today()

    games: list[dict] = []
    for game in raw_games:
        date_str = game.get("date")
        game_number = game.get("game_number")
        title = game.get("title")
        if not date_str or not game_number or not title:
            continue

        game_date = parse_game_date(date_str)
        if game_date <= today:
            continue

        card_text = format_card_text(title, game_number)
        games.append({
            "id": game.get("id"),
            "gameNumber": game_number,
            "rawTitle": title,
            "date": game_date.isoformat(),
            "cardText": card_text,
            "dateText": format_date_text(date_str),
            "cardFontSize": compute_card_font_size(card_text),
        })

    games.sort(key=lambda g: g["date"])
    return games
