from __future__ import annotations

import unittest

from quiz_backend import keynote


def items(*texts: str) -> list:
    return [{"index": i + 1, "x": 10.0, "y": 10.0 * (i + 1), "width": 100.0, "height": 40.0, "text": t}
            for i, t in enumerate(texts)]


class TemplatePlaceholdersTest(unittest.TestCase):
    def test_template_slide_has_number_and_name_placeholders(self):
        found = keynote.template_placeholders(items("ЗАМЕНИТЬ", "НОМЕР"))
        self.assertEqual(found, {"number": True, "name": True})

    def test_used_template_has_none(self):
        found = keynote.template_placeholders(items("ТРИНАДЦАТОЕ ", "Сами с собой не согласны"))
        self.assertEqual(found, {"number": False, "name": False})

    def test_half_filled_template(self):
        self.assertEqual(keynote.template_placeholders(items("НОМЕР", "Команда")), {"number": True, "name": False})

    def test_unrelated_slide(self):
        self.assertEqual(keynote.template_placeholders(items("Вопрос на точность")), {"number": False, "name": False})

    def test_is_template_requires_both_placeholders(self):
        self.assertTrue(keynote.is_template(items("ЗАМЕНИТЬ", "НОМЕР")))
        self.assertFalse(keynote.is_template(items("НОМЕР")))
        self.assertFalse(keynote.is_template(items("ЗАМЕНИТЬ", "3 место", "Команда,")))


class TemplateActionTest(unittest.TestCase):
    def test_extras_use_the_template(self):
        self.assertEqual(keynote.template_action(True, 3), "use")

    def test_unused_template_is_hidden(self):
        self.assertEqual(keynote.template_action(True, 0), "hide")

    def test_already_used_template_is_left_alone(self):
        self.assertEqual(keynote.template_action(False, 0), "none")

    def test_extras_without_a_template_are_an_error_for_the_caller(self):
        self.assertEqual(keynote.template_action(False, 2), "missing")


EXTRAS = [(13, "ТРИНАДЦАТОЕ", "Сами с собой"), (5, "ПЯТОЕ", "Чачка пипсов"), (4, "ЧЕТВЁРТОЕ", 'Команда "Четыре"')]
FIXED = [(1, 192, "Квизологи"), (2, 191, "Бета"), (3, 190, "Гамма")]


class BuildNamesScriptTest(unittest.TestCase):
    def script(self, assignments=FIXED, extras=EXTRAS, template_slide=189, hide=False) -> str:
        template = {"slide": template_slide, "extras": extras, "hide": hide}
        return keynote.build_names_script(assignments, "Квиз", template)

    def test_without_template_the_script_is_the_plain_replacement_one(self):
        script = keynote.build_names_script(FIXED, "Квиз")
        self.assertIn('set object text of ti to "Квизологи"', script)
        self.assertNotIn("duplicate", script)
        self.assertNotIn("skipped", script)

    def test_fixed_places_are_replaced_on_their_slides(self):
        script = self.script()
        for place, slide, team in FIXED:
            self.assertIn(f"slide {slide}", script)
            self.assertIn(f'"{team}"', script)

    def test_copies_are_made_before_the_template_one_fewer_than_extra_places(self):
        script = self.script()
        self.assertEqual(script.count("duplicate slide"), 2)
        self.assertIn("duplicate slide 189 to before slide 189", script)
        # после первой копии шаблон сдвигается на одну позицию вниз
        self.assertIn("duplicate slide 190 to before slide 190", script)
        self.assertNotIn("duplicate slide 191", script)

    def test_single_extra_place_needs_no_copies(self):
        script = self.script(extras=EXTRAS[:1])
        self.assertNotIn("duplicate", script)
        self.assertIn('"ТРИНАДЦАТОЕ"', script)

    def test_slides_are_filled_from_the_highest_place_down_to_the_template(self):
        script = self.script()
        # копии идут над шаблоном: 13-е на слайде 189, 5-е на 190, шаблон (190+1=191) — 4-е
        first = script.index('"ТРИНАДЦАТОЕ"')
        second = script.index('"ПЯТОЕ"')
        third = script.index('"ЧЕТВЁРТОЕ"')
        self.assertLess(first, second)
        self.assertLess(second, third)
        self.assertIn("set s to slide 189", script)
        self.assertIn("set s to slide 190", script)
        self.assertIn("set s to slide 191", script)

    def test_number_and_name_placeholders_are_both_replaced_with_escaping(self):
        script = self.script()
        self.assertIn('"НОМЕР"', script)
        self.assertIn('"ЗАМЕНИТЬ"', script)
        self.assertIn('Команда \\"Четыре\\"', script)

    def test_fixed_places_are_done_before_any_slide_is_duplicated(self):
        script = self.script()
        self.assertLess(script.index('"Квизологи"'), script.index("duplicate slide"))
        self.assertLess(script.index('"Гамма"'), script.index("duplicate slide"))

    def test_used_slides_are_made_visible(self):
        script = self.script()
        self.assertEqual(script.count("set skipped of s to false"), 3)

    def test_unused_template_can_be_hidden_from_the_show(self):
        script = self.script(extras=[], hide=True)
        self.assertIn("set skipped of slide 189 to true", script)
        self.assertNotIn("duplicate", script)
        self.assertNotIn('"НОМЕР"', script)

    def test_long_ordinal_is_scaled_down_from_the_template_font_size(self):
        extras = [(28, "ДВАДЦАТЬ ВОСЬМОЕ", "Альфа")]
        script = self.script(assignments=[], extras=extras)
        self.assertIn("set baseSize to size of object text of ti", script)
        self.assertIn("baseSize * 0.8125", script)

    def test_short_ordinals_keep_their_font_untouched(self):
        script = self.script(assignments=[], extras=[(9, "ДЕВЯТОЕ", "Альфа")])
        self.assertNotIn("baseSize", script)

    def test_team_name_font_is_never_scaled(self):
        script = self.script(assignments=[], extras=[(28, "ДВАДЦАТЬ ВОСЬМОЕ", "Альфа")])
        self.assertEqual(script.count("baseSize * "), 1)

    def test_message_reports_replaced_and_created_slides(self):
        # 3 слайда фиксированных мест + 3 слайда дополнительных, из них 2 — новые копии шаблона
        self.assertIn("заменено слайдов — 6", self.script())
        self.assertIn("создано новых — 2", self.script())

    def test_missing_placeholder_on_a_slide_is_a_keynote_error(self):
        script = self.script()
        self.assertIn('error "Не найден текст', script)


if __name__ == "__main__":
    unittest.main()
