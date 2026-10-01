from __future__ import annotations

import unittest

from quiz_backend import excel
from quiz_backend.errors import BackendError

from .helpers import workbook_bytes

HEADER = ["Место", "Команда", "Итого"] + [f"Раунд {i}" for i in range(1, 10)]


class ReadTeamsTest(unittest.TestCase):
    def test_reads_place_name_total_and_requested_number_of_rounds(self):
        data = workbook_bytes([
            HEADER,
            [1, "Альфа", 30, 10, 8, 12],
            [2, "Бета", 25, 9, 7, 9],
        ])
        self.assertEqual(excel.read_teams(data, rounds=3), [
            {"place": 1, "name": "Альфа", "total": 30, "rounds": [10, 8, 12]},
            {"place": 2, "name": "Бета", "total": 25, "rounds": [9, 7, 9]},
        ])

    def test_takes_exactly_n_round_columns_from_d(self):
        row = [1, "Альфа", 80] + [10, 20, 30, 40, 50, 60, 70, 80, 90]  # 9 колонок раундов в таблице
        data = workbook_bytes([HEADER, row])
        self.assertEqual(excel.read_teams(data, rounds=8)[0]["rounds"], [10, 20, 30, 40, 50, 60, 70, 80])
        self.assertEqual(excel.read_teams(data, rounds=7)[0]["rounds"], [10, 20, 30, 40, 50, 60, 70])

    def test_missing_round_columns_become_empty(self):
        data = workbook_bytes([HEADER[:5], [1, "Альфа", 30, 10, 8]])
        self.assertEqual(excel.read_teams(data, rounds=4)[0]["rounds"], [10, 8, None, None])

    def test_empty_cell_stays_empty(self):
        data = workbook_bytes([HEADER, [1, "Альфа", 30, 10, None, 12]])
        self.assertEqual(excel.read_teams(data, rounds=3)[0]["rounds"], [10, None, 12])

    def test_zero_rounds_means_no_round_values(self):
        data = workbook_bytes([HEADER, [1, "Альфа", 30, 10, 8]])
        team = excel.read_teams(data)[0]
        self.assertEqual(team["rounds"], [])
        self.assertEqual(team["name"], "Альфа")

    def test_first_row_is_header_and_is_skipped(self):
        data = workbook_bytes([[1, "Заголовок-похожий-на-данные", 0], [2, "Бета", 25]])
        self.assertEqual([t["name"] for t in excel.read_teams(data)], ["Бета"])

    def test_stops_at_first_row_without_place_or_name(self):
        data = workbook_bytes([
            HEADER,
            [1, "Альфа", 30],
            [None, None, None],
            [2, "Бета", 25],
        ])
        self.assertEqual([t["name"] for t in excel.read_teams(data)], ["Альфа"])

    def test_float_place_becomes_int(self):
        data = workbook_bytes([HEADER, [1.0, "Альфа", 30.5]])
        team = excel.read_teams(data)[0]
        self.assertEqual(team["place"], 1)
        self.assertIsInstance(team["place"], int)
        self.assertEqual(team["total"], 30.5)

    def test_narrow_sheet_does_not_crash(self):
        data = workbook_bytes([["Место", "Команда"], [1, "Альфа"]])
        self.assertEqual(excel.read_teams(data, rounds=2),
                         [{"place": 1, "name": "Альфа", "total": None, "rounds": [None, None]}])


class SheetSelectionTest(unittest.TestCase):
    def test_missing_sheet_lists_available_sheets(self):
        data = workbook_bytes([HEADER], title="Результаты", other_sheets={"Архив": [HEADER]})
        with self.assertRaises(BackendError) as ctx:
            excel.read_teams(data)
        self.assertEqual(ctx.exception.code, "EXCEL_BAD_FORMAT")
        self.assertIn("Лист1", ctx.exception.message)
        self.assertIn("Результаты", ctx.exception.message)
        self.assertIn("Архив", ctx.exception.message)

    def test_similar_sheet_name_is_not_guessed(self):
        data = workbook_bytes([HEADER, [1, "Не та", 1]], title="Лист1 (копия)")
        with self.assertRaises(BackendError) as ctx:
            excel.read_teams(data)
        self.assertEqual(ctx.exception.code, "EXCEL_BAD_FORMAT")

    def test_reads_sheet1_even_when_it_is_not_the_first_sheet(self):
        data = workbook_bytes([HEADER, [1, "Копия", 1]], title="Лист1 (копия)",
                              other_sheets={"Лист1": [HEADER, [1, "Оригинал", 2]]})
        self.assertEqual(excel.read_teams(data)[0]["name"], "Оригинал")


class BadInputTest(unittest.TestCase):
    def test_garbage_bytes_are_bad_format(self):
        with self.assertRaises(BackendError) as ctx:
            excel.read_teams("это совсем не xlsx".encode("utf-8"))
        self.assertEqual(ctx.exception.code, "EXCEL_BAD_FORMAT")

    def test_empty_bytes_are_bad_format(self):
        with self.assertRaises(BackendError) as ctx:
            excel.read_teams(b"")
        self.assertEqual(ctx.exception.code, "EXCEL_BAD_FORMAT")


class TeamsByPlaceTest(unittest.TestCase):
    def test_maps_place_to_name(self):
        teams = [{"place": 1, "name": "Альфа"}, {"place": 2.0, "name": "Бета"}]
        self.assertEqual(excel.teams_by_place(teams), {1: "Альфа", 2: "Бета"})


if __name__ == "__main__":
    unittest.main()
