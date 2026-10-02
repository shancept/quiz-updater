from __future__ import annotations

import unittest

from quiz_backend.errors import BackendError
from quiz_backend.ordinals import ordinal_font_scale, ordinal_place


class OrdinalPlaceTest(unittest.TestCase):
    """Порядковые числительные среднего рода («место» — среднего рода): девятое, четырнадцатое…"""

    def test_units(self):
        expected = ["первое", "второе", "третье", "четвёртое", "пятое", "шестое", "седьмое", "восьмое", "девятое"]
        self.assertEqual([ordinal_place(n) for n in range(1, 10)], expected)

    def test_ten_to_nineteen(self):
        expected = [
            "десятое", "одиннадцатое", "двенадцатое", "тринадцатое", "четырнадцатое",
            "пятнадцатое", "шестнадцатое", "семнадцатое", "восемнадцатое", "девятнадцатое",
        ]
        self.assertEqual([ordinal_place(n) for n in range(10, 20)], expected)

    def test_round_tens(self):
        expected = {
            20: "двадцатое", 30: "тридцатое", 40: "сороковое", 50: "пятидесятое",
            60: "шестидесятое", 70: "семидесятое", 80: "восьмидесятое", 90: "девяностое", 100: "сотое",
        }
        for number, word in expected.items():
            self.assertEqual(ordinal_place(number), word, number)

    def test_compound_numbers_use_cardinal_tens(self):
        expected = {
            21: "двадцать первое", 22: "двадцать второе", 28: "двадцать восьмое",
            34: "тридцать четвёртое", 45: "сорок пятое", 59: "пятьдесят девятое",
            67: "шестьдесят седьмое", 76: "семьдесят шестое", 88: "восемьдесят восьмое",
            99: "девяносто девятое",
        }
        for number, word in expected.items():
            self.assertEqual(ordinal_place(number), word, number)

    def test_third_is_irregular_in_compounds_too(self):
        for number, word in {23: "двадцать третье", 33: "тридцать третье", 43: "сорок третье", 93: "девяносто третье"}.items():
            self.assertEqual(ordinal_place(number), word, number)

    def test_user_examples(self):
        self.assertEqual(ordinal_place(9), "девятое")
        self.assertEqual(ordinal_place(14), "четырнадцатое")

    def test_all_values_1_to_100_are_distinct_non_empty_words(self):
        words = [ordinal_place(n) for n in range(1, 101)]
        self.assertEqual(len(set(words)), 100)
        self.assertTrue(all(word and word == word.lower() for word in words))

    def test_every_word_ends_like_a_neuter_adjective(self):
        for n in range(1, 101):
            self.assertRegex(ordinal_place(n), r"(ое|ье)$", n)

    def test_out_of_range_is_rejected(self):
        for bad in (0, -3, 101):
            with self.assertRaises(BackendError) as ctx:
                ordinal_place(bad)
            self.assertEqual(ctx.exception.code, "INVALID_ARGUMENT")


class OrdinalFontScaleTest(unittest.TestCase):
    """Длинное числительное в поле «НОМЕР» не должно вылезать за слайд или переноситься на вторую строку
    (проверено на слайде: «ДВАДЦАТЬ ВОСЬМОЕ» упирается в края, «ВОСЕМЬДЕСЯТ ВОСЬМОЕ» налезает на «МЕСТО»)."""

    def test_words_that_fit_keep_the_template_font_size(self):
        for text in ("ПЯТОЕ", "ТРИНАДЦАТОЕ", "ЧЕТЫРНАДЦАТОЕ"):  # до 13 букв включительно помещаются
            self.assertEqual(ordinal_font_scale(text), 1.0, text)

    def test_longer_text_is_scaled_down_in_proportion_to_its_length(self):
        self.assertAlmostEqual(ordinal_font_scale("ДВАДЦАТЬ ВОСЬМОЕ"), 13 / 16)
        self.assertAlmostEqual(ordinal_font_scale("ВОСЕМЬДЕСЯТ ВОСЬМОЕ"), 13 / 19)

    def test_scale_never_exceeds_one_and_stays_readable_for_every_supported_place(self):
        for n in range(1, 101):
            scale = ordinal_font_scale(ordinal_place(n).upper())
            self.assertTrue(0.6 <= scale <= 1.0, (n, scale))


if __name__ == "__main__":
    unittest.main()
