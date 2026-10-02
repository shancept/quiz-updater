from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "sheets", "SortResults.gs")
HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sheet_script_harness.js")


def js(fn: str, *args):
    """Вызывает функцию скрипта таблицы (JavaScript) и возвращает её результат."""
    proc = subprocess.run(
        ["osascript", "-l", "JavaScript", HARNESS, SCRIPT],
        input=json.dumps({"fn": fn, "args": list(args)}).encode("utf-8"),
        capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr.decode("utf-8", errors="replace"))
    return json.loads(proc.stdout.decode("utf-8"))["result"]


def apply_plan(rows: list, keys: list) -> list:
    """Как Google Sheets применяет несколько ключей сортировки: первый ключ главный; пустые ячейки всегда в конце.

    Эталонная реализация для проверки, что план даёт нужный порядок. Реальную сортировку выполняет сама таблица.
    """
    ordered = list(rows)
    for key in reversed(keys):  # устойчивая сортировка: сначала младший ключ, главный — последним
        offset, ascending = key["offset"], key["ascending"]
        filled = [r for r in ordered if r[offset] not in ("", None)]
        blank = [r for r in ordered if r[offset] in ("", None)]
        if isinstance(filled[0][offset], str) if filled else False:
            filled.sort(key=lambda r: r[offset].lower(), reverse=not ascending)
        else:
            filled.sort(key=lambda r: r[offset], reverse=not ascending)
        ordered = filled + blank
    return ordered


@unittest.skipUnless(shutil.which("osascript"), "нужен osascript (macOS)")
class LeadingFilledTest(unittest.TestCase):
    def test_counts_cells_until_the_first_empty_one(self):
        self.assertEqual(js("leadingFilled", [1, 2, "", 3]), 2)

    def test_empty_first_cell_gives_zero(self):
        self.assertEqual(js("leadingFilled", ["", 1]), 0)
        self.assertEqual(js("leadingFilled", []), 0)

    def test_zero_is_a_value(self):
        self.assertEqual(js("leadingFilled", [0, 0, ""]), 2)

    def test_names_and_headers_are_counted_the_same_way(self):
        self.assertEqual(js("leadingFilled", ["Альфа", "Бета", "", "Гамма"]), 2)


@unittest.skipUnless(shutil.which("osascript"), "нужен osascript (macOS)")
class PlanSortTest(unittest.TestCase):
    # строка = [название, итого, раунд 1, раунд 2, …]; offset 0 — название, 1 — итого, 2 — раунд 1…
    def plan(self, rows: list) -> dict:
        return js("planSort", rows)

    def keys(self, rows: list) -> list:
        return [(k["offset"], k["ascending"]) for k in self.plan(rows)["keys"]]

    def test_total_is_the_main_key_then_rounds_from_last_to_first_then_name(self):
        rows = [["А", 30, 10, 20], ["Б", 25, 15, 10]]
        self.assertEqual(self.keys(rows), [(1, False), (3, False), (2, False), (0, True)])
        self.assertEqual(self.plan(rows)["rounds"], 2)

    def test_empty_round_cuts_off_it_and_all_following_rounds(self):
        # раунд 1 есть, раунд 2 пуст, раунд 3 заполнен — раунд 3 не используется
        rows = [["А", 10, 10, "", 5], ["Б", 8, 8, "", 9]]
        self.assertEqual(self.plan(rows)["rounds"], 1)
        self.assertEqual(self.keys(rows), [(1, False), (2, False), (0, True)])

    def test_rounds_1_to_3_filled_and_4_empty(self):
        rows = [["А", 6, 1, 2, 3, ""], ["Б", 5, 3, 2, 0, ""]]
        self.assertEqual(self.plan(rows)["rounds"], 3)
        self.assertEqual(self.keys(rows), [(1, False), (4, False), (3, False), (2, False), (0, True)])

    def test_no_rounds_played_still_sorts_total_and_name(self):
        rows = [["А", 0, "", ""], ["Б", 0, "", ""]]
        self.assertEqual(self.plan(rows)["rounds"], 0)
        self.assertEqual(self.keys(rows), [(1, False), (0, True)])

    def test_round_counts_as_played_if_at_least_one_team_has_a_value(self):
        rows = [["А", 5, 5, ""], ["Б", 0, "", ""]]
        self.assertEqual(self.plan(rows)["rounds"], 1)

    def test_zero_score_counts_as_a_played_round(self):
        rows = [["А", 0, 0], ["Б", 0, 0]]
        self.assertEqual(self.plan(rows)["rounds"], 1)

    def test_table_without_round_columns(self):
        self.assertEqual(self.keys([["А", 3], ["Б", 4]]), [(1, False), (0, True)])


@unittest.skipUnless(shutil.which("osascript"), "нужен osascript (macOS)")
class OrderingTest(unittest.TestCase):
    """Порядок, который получится у ведущего. Строка = [название, итого, раунды…]."""

    def sorted_names(self, rows: list) -> list:
        plan = js("planSort", rows)
        return [r[0] for r in apply_plan(rows, plan["keys"])]

    def test_higher_total_goes_first(self):
        rows = [["Б", 10, 10], ["А", 30, 30], ["В", 20, 20]]
        self.assertEqual(self.sorted_names(rows), ["А", "В", "Б"])

    def test_equal_totals_are_decided_by_the_last_played_round(self):
        rows = [["Б", 20, 10, 10], ["А", 20, 15, 5], ["В", 20, 5, 15]]
        self.assertEqual(self.sorted_names(rows), ["В", "Б", "А"])

    def test_if_last_round_is_equal_the_previous_one_decides(self):
        rows = [["А", 20, 4, 6, 10], ["Б", 20, 6, 4, 10]]
        self.assertEqual(self.sorted_names(rows), ["А", "Б"])  # раунд 2: 6 > 4

    def test_fully_equal_teams_go_by_name_alphabetically_ignoring_case(self):
        rows = [["яблоки", 10, 10], ["Арбузы", 10, 10], ["бананы", 10, 10]]
        self.assertEqual(self.sorted_names(rows), ["Арбузы", "бананы", "яблоки"])

    def test_unplayed_round_with_stray_values_is_ignored_as_the_host_asked(self):
        # раунд 2 пуст, в раунде 3 у «Б» больше — но он не учитывается: решает раунд 1
        rows = [["Б", 10, 3, "", 7], ["А", 10, 5, "", 5]]
        self.assertEqual(self.sorted_names(rows), ["А", "Б"])

    def test_before_the_first_round_only_total_and_name_matter(self):
        rows = [["Б", 5, "", ""], ["А", 5, "", ""], ["В", 9, "", ""]]
        self.assertEqual(self.sorted_names(rows), ["В", "А", "Б"])

    def test_team_without_a_score_in_a_played_round_goes_after_those_with_scores(self):
        rows = [["Б", 10, "", 10], ["А", 10, 10, 10]]
        self.assertEqual(self.sorted_names(rows), ["А", "Б"])


@unittest.skipUnless(shutil.which("osascript"), "нужен osascript (macOS)")
class SourceSafetyTest(unittest.TestCase):
    def setUp(self):
        with open(SCRIPT, encoding="utf-8") as fh:
            self.source = fh.read()

    def test_script_may_touch_only_the_spreadsheet_it_lives_in(self):
        # Узкое разрешение: Google покажет «просматривать и изменять только эту таблицу», а не весь Drive.
        self.assertIn("@OnlyCurrentDoc", self.source)

    def test_script_has_menu_and_entry_point_for_the_button(self):
        self.assertIn("function onOpen", self.source)
        self.assertIn("function sortResults", self.source)

    def test_script_does_not_reach_outside_the_spreadsheet(self):
        for forbidden in ("UrlFetchApp", "DriveApp", "MailApp", "GmailApp", "ScriptApp.newTrigger"):
            self.assertNotIn(forbidden, self.source)


if __name__ == "__main__":
    unittest.main()
