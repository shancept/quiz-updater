from __future__ import annotations

import unittest
from unittest import mock

from quiz_backend import keynote
from quiz_backend.errors import BackendError


class RoundsFromTableOutputTest(unittest.TestCase):
    def test_rounds_are_columns_minus_place_team_total(self):
        self.assertEqual(keynote.rounds_from_table_output("10", slide_num=81), 7)
        self.assertEqual(keynote.rounds_from_table_output("11", slide_num=81), 8)

    def test_output_with_whitespace(self):
        self.assertEqual(keynote.rounds_from_table_output(" 11\n", slide_num=81), 8)

    def test_table_with_only_fixed_columns_has_zero_rounds(self):
        self.assertEqual(keynote.rounds_from_table_output("3", slide_num=81), 0)

    def test_too_few_columns_is_invalid_template(self):
        with self.assertRaises(BackendError) as ctx:
            keynote.rounds_from_table_output("2", slide_num=81)
        self.assertEqual(ctx.exception.code, "TEMPLATE_INVALID")
        self.assertIn("81", ctx.exception.message)

    def test_slide_without_table_is_invalid_template(self):
        with self.assertRaises(BackendError) as ctx:
            keynote.rounds_from_table_output(keynote.NO_TABLE_MARKER, slide_num=81)
        self.assertEqual(ctx.exception.code, "TEMPLATE_INVALID")
        self.assertIn("81", ctx.exception.message)
        self.assertIn("таблиц", ctx.exception.message)

    def test_unparseable_output_is_reported(self):
        with self.assertRaises(BackendError) as ctx:
            keynote.rounds_from_table_output("что-то странное", slide_num=81)
        self.assertEqual(ctx.exception.code, "APPLESCRIPT_ERROR")


class ReadRatingRoundsTest(unittest.TestCase):
    def test_script_is_read_only_and_targets_table_1_of_the_slide(self):
        script = keynote.build_rating_columns_script('Квиз "Классика"', 81)
        self.assertIn('document "Квиз \\"Классика\\""', script)
        self.assertIn("slide 81", script)
        self.assertIn("table 1", script)
        self.assertIn("column count", script)
        self.assertNotIn("set value", script)

    def test_reads_rounds_through_applescript(self):
        with mock.patch.object(keynote, "run_applescript", return_value="11") as run:
            self.assertEqual(keynote.read_rating_rounds("Квиз", 81), 8)
        self.assertIn("column count", run.call_args[0][0])


class BuildRatingScriptTest(unittest.TestCase):
    """Характеризация: скрипт пишет столько раундов, сколько их в данных (и 8, и 7)."""

    def _teams(self, rounds: int) -> list:
        return [{"place": 1, "name": "Альфа", "total": 80, "rounds": list(range(10, 10 + rounds))}]

    def test_eight_rounds_fill_columns_4_to_11(self):
        script = keynote.build_rating_script(self._teams(8), 81, "Квиз")
        self.assertIn("set value of cell 11 of row 1 of t to 17", script)
        self.assertNotIn("cell 12", script)

    def test_seven_rounds_fill_columns_4_to_10(self):
        script = keynote.build_rating_script(self._teams(7), 81, "Квиз")
        self.assertIn("set value of cell 10 of row 1 of t to 16", script)
        self.assertNotIn("cell 11", script)

    def test_empty_round_becomes_empty_cell(self):
        teams = [{"place": 1, "name": "Альфа", "total": 5, "rounds": [None, 5]}]
        script = keynote.build_rating_script(teams, 81, "Квиз")
        self.assertIn('set value of cell 4 of row 1 of t to ""', script)


if __name__ == "__main__":
    unittest.main()
