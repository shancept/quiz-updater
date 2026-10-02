from __future__ import annotations

import unittest

from quiz_backend.applescript import slide_not_found_error

RU_SLIDE = ('86:95: execution error: Получена ошибка от «Keynote»: Не удается получить slide 193 of document '
            '"Игра #1244 World.key". Неверный индекс. (-1719)')
EN_SLIDE = '86:95: execution error: Keynote got an error: Can’t get slide 193 of document "Game.key". Invalid index. (-1719)'
RU_TABLE = ('86:95: execution error: Получена ошибка от «Keynote»: Не удается получить table 1 of slide 1 of '
            'document "Игра.key". Неверный индекс. (-1719)')


class SlideNotFoundErrorTest(unittest.TestCase):
    def test_missing_slide_is_reported_with_its_number(self):
        error = slide_not_found_error(RU_SLIDE)
        self.assertEqual(error.code, "SLIDE_NOT_FOUND")
        self.assertIn("193", error.message)
        self.assertNotIn("AppleScript", error.message)
        self.assertNotIn("-1719", error.message)

    def test_message_tells_the_host_what_to_do(self):
        message = slide_not_found_error(RU_SLIDE).message
        self.assertIn("заново", message)

    def test_english_keynote_is_recognised_too(self):
        self.assertEqual(slide_not_found_error(EN_SLIDE).code, "SLIDE_NOT_FOUND")

    def test_missing_table_on_an_existing_slide_is_not_a_missing_slide(self):
        self.assertIsNone(slide_not_found_error(RU_TABLE))

    def test_unrelated_errors_are_left_alone(self):
        self.assertIsNone(slide_not_found_error("execution error: что-то ещё (-1700)"))
        self.assertIsNone(slide_not_found_error(""))


if __name__ == "__main__":
    unittest.main()
