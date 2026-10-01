from __future__ import annotations

import unittest
from unittest import mock

from quiz_backend import keynote
from quiz_backend.errors import BackendError


class ParseRatingTableTest(unittest.TestCase):
    def parse(self, output: str, slide_num: int = 81) -> dict:
        return keynote.parse_rating_table(output, slide_num=slide_num)

    def test_reads_columns_rows_height_and_font(self):
        self.assertEqual(
            self.parse("10\t25\t568,0\t22,0"),
            {"columns": 10, "rows": 25, "height": 568.0, "font_size": 22.0, "rounds": 7},
        )

    def test_rounds_are_columns_minus_place_team_total(self):
        self.assertEqual(self.parse("11\t10\t400\t20")["rounds"], 8)
        self.assertEqual(self.parse("10\t10\t400\t20")["rounds"], 7)

    def test_decimal_dot_is_accepted_too(self):
        self.assertEqual(self.parse("10\t25\t568.5\t22.5")["height"], 568.5)

    def test_surrounding_whitespace_is_ignored(self):
        self.assertEqual(self.parse(" 11\t10\t400\t20\n")["columns"], 11)

    def test_unreadable_font_is_none(self):
        self.assertIsNone(self.parse("10\t25\t568\t0")["font_size"])

    def test_table_with_only_fixed_columns_has_zero_rounds(self):
        self.assertEqual(self.parse("3\t10\t400\t20")["rounds"], 0)

    def test_too_few_columns_is_invalid_template(self):
        with self.assertRaises(BackendError) as ctx:
            self.parse("2\t10\t400\t20")
        self.assertEqual(ctx.exception.code, "TEMPLATE_INVALID")
        self.assertIn("81", ctx.exception.message)

    def test_slide_without_table_is_invalid_template(self):
        with self.assertRaises(BackendError) as ctx:
            self.parse(keynote.NO_TABLE_MARKER)
        self.assertEqual(ctx.exception.code, "TEMPLATE_INVALID")
        self.assertIn("81", ctx.exception.message)
        self.assertIn("таблиц", ctx.exception.message)

    def test_unparseable_output_is_reported(self):
        for output in ("что-то странное", "10", "10\t25\tx\ty"):
            with self.assertRaises(BackendError) as ctx:
                self.parse(output)
            self.assertEqual(ctx.exception.code, "APPLESCRIPT_ERROR", output)


class ReadRatingTableTest(unittest.TestCase):
    def test_script_is_read_only_and_targets_table_1_of_the_slide(self):
        script = keynote.build_rating_table_script('Квиз "Классика"', 81)
        self.assertIn('document "Квиз \\"Классика\\""', script)
        self.assertIn("slide 81", script)
        self.assertIn("table 1", script)
        for needed in ("column count", "row count", "height of", "font size"):
            self.assertIn(needed, script)
        self.assertNotIn("set value", script)
        self.assertNotIn("set row count", script)

    def test_reads_table_through_applescript(self):
        with mock.patch.object(keynote, "run_applescript", return_value="11\t10\t400,0\t20,0") as run:
            table = keynote.read_rating_table("Квиз", 81)
        self.assertEqual(table["rounds"], 8)
        self.assertEqual(table["rows"], 10)
        self.assertIn("column count", run.call_args[0][0])


class PlanRowChangeTest(unittest.TestCase):
    def plan(self, current: int, target: int, height: float = 568.0, font: float = 22.0) -> dict:
        return keynote.plan_row_change(current, target, height, font)

    def test_adding_rows(self):
        plan = self.plan(10, 15)
        self.assertEqual((plan["added"], plan["removed"], plan["warnings"]), (5, 0, []))

    def test_removing_rows(self):
        plan = self.plan(10, 8)
        self.assertEqual((plan["added"], plan["removed"], plan["warnings"]), (0, 2, []))

    def test_same_number_of_rows_changes_nothing(self):
        plan = self.plan(10, 10)
        self.assertEqual((plan["added"], plan["removed"]), (0, 0))

    def test_plan_reports_current_and_target(self):
        plan = self.plan(10, 8)
        self.assertEqual((plan["currentRows"], plan["targetRows"]), (10, 8))

    def test_warns_when_new_rows_become_too_thin_for_the_font(self):
        # Keynote держит высоту таблицы постоянной: 568 pt / 25 = 22,7 pt на строку при шрифте 22 pt.
        warnings = self.plan(10, 25)["warnings"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("25", warnings[0])
        self.assertIn("pt", warnings[0])
        self.assertIn("22", warnings[0])

    def test_boundary_exactly_fitting_row_height_does_not_warn(self):
        self.assertEqual(self.plan(10, 20, height=520.0, font=20.0)["warnings"], [])  # 26 pt == 20 * 1.3
        self.assertEqual(len(self.plan(10, 21, height=520.0, font=20.0)["warnings"]), 1)  # 24,8 pt < 26

    def test_removing_rows_never_warns_even_if_table_is_tight(self):
        self.assertEqual(self.plan(40, 30, height=400.0, font=22.0)["warnings"], [])

    def test_unchanged_tight_table_does_not_warn(self):
        self.assertEqual(self.plan(30, 30, height=400.0, font=22.0)["warnings"], [])

    def test_unknown_font_gives_no_warning(self):
        self.assertEqual(keynote.plan_row_change(10, 50, 568.0, None)["warnings"], [])


class BuildRatingScriptTest(unittest.TestCase):
    """Скрипт пишет столько раундов, сколько их в данных (и 8, и 7), и подгоняет число строк."""

    def _teams(self, rounds: int, count: int = 1) -> list:
        return [
            {"place": i + 1, "name": f"Команда {i + 1}", "total": 80, "rounds": list(range(10, 10 + rounds))}
            for i in range(count)
        ]

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

    def test_row_count_is_set_to_the_number_of_teams_only_when_it_differs(self):
        script = keynote.build_rating_script(self._teams(7, count=8), 81, "Квиз")
        self.assertIn("if (row count of t) is not 8 then set row count of t to 8", script)

    def test_rows_are_resized_before_any_cell_is_written(self):
        script = keynote.build_rating_script(self._teams(7, count=3), 81, "Квиз")
        self.assertLess(script.index("set row count of t to 3"), script.index("set value of cell"))

    def test_too_few_keynote_rows_is_no_longer_an_error(self):
        script = keynote.build_rating_script(self._teams(7, count=30), 81, "Квиз")
        self.assertNotIn("В таблице Keynote только", script)
        self.assertIn("set row count of t to 30", script)

    def test_last_row_is_written(self):
        script = keynote.build_rating_script(self._teams(7, count=8), 81, "Квиз")
        self.assertIn("set value of cell 2 of row 8 of t to", script)
        self.assertNotIn("row 9 of t", script)


if __name__ == "__main__":
    unittest.main()
