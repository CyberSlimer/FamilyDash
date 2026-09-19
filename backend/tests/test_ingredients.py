"""
Tests for ingredient parsing, unit maths and the inventory helpers.

Run from the backend/ directory:
    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ingredients as ing  # noqa: E402


class ParseQuantityTests(unittest.TestCase):
    def test_plain_numbers(self):
        self.assertEqual(ing.parse_quantity('2 cups flour'), (2.0, 'cups flour'))
        self.assertEqual(ing.parse_quantity('1.5 lb beef'), (1.5, 'lb beef'))
        self.assertEqual(ing.parse_quantity('.5 cup milk'), (0.5, 'cup milk'))

    def test_fractions(self):
        self.assertEqual(ing.parse_quantity('1/2 cup')[0], 0.5)
        self.assertEqual(ing.parse_quantity('1 1/2 cups')[0], 1.5)
        self.assertEqual(ing.parse_quantity('3/4 tsp')[0], 0.75)

    def test_vulgar_fractions(self):
        self.assertEqual(ing.parse_quantity('½ cup milk')[0], 0.5)
        self.assertEqual(ing.parse_quantity('1½ cups')[0], 1.5)
        self.assertAlmostEqual(ing.parse_quantity('⅓ cup')[0], 1 / 3)

    def test_ranges_take_the_upper_bound(self):
        # Better to buy one too many onions than to come home short.
        self.assertEqual(ing.parse_quantity('2-3 cloves')[0], 3.0)
        self.assertEqual(ing.parse_quantity('2 to 3 apples')[0], 3.0)
        self.assertEqual(ing.parse_quantity('1–2 lemons')[0], 2.0)

    def test_no_quantity(self):
        self.assertEqual(ing.parse_quantity('Salt to taste'), (None, 'Salt to taste'))
        self.assertEqual(ing.parse_quantity(''), (None, ''))


class UnitTests(unittest.TestCase):
    def test_canonical(self):
        self.assertEqual(ing.canonical_unit('cups'), 'cup')
        self.assertEqual(ing.canonical_unit('lbs'), 'lb')
        self.assertEqual(ing.canonical_unit('Tbsp.'), 'tbsp')
        self.assertEqual(ing.canonical_unit('ounces'), 'oz')
        self.assertEqual(ing.canonical_unit('cloves'), 'clove')
        self.assertEqual(ing.canonical_unit('banana'), '')

    def test_capital_T_is_tablespoon(self):
        self.assertEqual(ing.canonical_unit('T'), 'tbsp')
        self.assertEqual(ing.canonical_unit('t'), 'tsp')

    def test_conversion(self):
        self.assertAlmostEqual(ing.convert(1, 'lb', 'oz'), 16.0, places=3)
        self.assertAlmostEqual(ing.convert(2, 'cup', 'tbsp'), 32.0, places=1)
        self.assertAlmostEqual(ing.convert(1000, 'g', 'kg'), 1.0, places=6)

    def test_incompatible_dimensions(self):
        self.assertFalse(ing.compatible('cup', 'lb'))
        self.assertIsNone(ing.convert(1, 'cup', 'lb'))

    def test_container_units_do_not_cross(self):
        # 2 cans is not 2 heads of lettuce.
        self.assertFalse(ing.compatible('can', 'head'))
        self.assertTrue(ing.compatible('can', 'can'))
        self.assertTrue(ing.compatible('each', 'dozen'))


class FormatTests(unittest.TestCase):
    def test_whole_numbers(self):
        self.assertEqual(ing.format_quantity(3.0), '3')
        self.assertEqual(ing.format_quantity(3), '3')

    def test_fractions_read_like_a_recipe(self):
        self.assertEqual(ing.format_quantity(0.5), '1/2')
        self.assertEqual(ing.format_quantity(1.5), '1 1/2')
        self.assertEqual(ing.format_quantity(0.75), '3/4')

    def test_amount_hides_the_generic_unit(self):
        self.assertEqual(ing.format_amount(3, 'each'), '3')
        self.assertEqual(ing.format_amount(None, ''), '')

    def test_word_units_are_pluralised(self):
        self.assertEqual(ing.format_amount(2, 'cup'), '2 cups')
        self.assertEqual(ing.format_amount(1, 'cup'), '1 cup')
        self.assertEqual(ing.format_amount(3, 'clove'), '3 cloves')
        self.assertEqual(ing.format_amount(2, 'loaf'), '2 loaves')
        self.assertEqual(ing.format_amount(2, 'bunch'), '2 bunches')

    def test_abbreviations_are_not_pluralised(self):
        self.assertEqual(ing.format_amount(2, 'tbsp'), '2 tbsp')
        self.assertEqual(ing.format_amount(2, 'lb'), '2 lb')
        self.assertEqual(ing.format_amount(15, 'oz'), '15 oz')

    def test_fractions_below_one_stay_singular(self):
        self.assertEqual(ing.format_amount(0.5, 'cup'), '1/2 cups')


class UnitPrecisionTests(unittest.TestCase):
    """Rounded unit factors used to break clean fractions; keep them exact."""

    def test_customary_volumes_are_exact_multiples(self):
        self.assertEqual(ing.convert(1, 'quart', 'cup'), 4.0)
        self.assertEqual(ing.convert(1, 'gallon', 'cup'), 16.0)
        self.assertEqual(ing.convert(1, 'cup', 'tbsp'), 16.0)
        self.assertEqual(ing.convert(1, 'tbsp', 'tsp'), 3.0)
        self.assertEqual(ing.convert(1, 'pint', 'cup'), 2.0)

    def test_pound_is_exactly_sixteen_ounces(self):
        self.assertEqual(ing.convert(1, 'lb', 'oz'), 16.0)

    def test_converted_totals_still_print_as_fractions(self):
        # "2 cups + 1 quart" printed as "1.5 quart" when the factors were rounded.
        self.assertEqual(ing.format_amount(*ing.add_amounts(1, 'quart', 2, 'cup')),
                         '1 1/2 quarts')
        self.assertEqual(ing.format_amount(*ing.add_amounts(1, 'lb', 8, 'oz')),
                         '1 1/2 lb')
        self.assertEqual(ing.format_amount(*ing.add_amounts(1, 'cup', 8, 'tbsp')),
                         '1 1/2 cups')


class NormalizeTests(unittest.TestCase):
    def test_plural_and_case(self):
        self.assertEqual(ing.normalize_name('Bell Peppers'), 'bell pepper')
        self.assertEqual(ing.normalize_name('tomatoes'), 'tomato')
        self.assertEqual(ing.normalize_name('Berries'), 'berry')

    def test_prep_clause_dropped(self):
        self.assertEqual(ing.normalize_name('onion, diced'), 'onion')
        self.assertEqual(ing.normalize_name('garlic, finely minced'), 'garlic')

    def test_noise_words_dropped(self):
        self.assertEqual(ing.normalize_name('fresh organic large eggs'), 'egg')

    def test_meaningful_words_kept(self):
        # 'ground beef' and 'beef' are different things to buy.
        self.assertEqual(ing.normalize_name('ground beef'), 'ground beef')
        self.assertEqual(ing.normalize_name('crushed tomatoes'), 'crushed tomato')

    def test_matching_across_lists(self):
        self.assertEqual(ing.normalize_name('3 Bell Peppers'.split(' ', 1)[1]),
                         ing.normalize_name('bell pepper'))


class ParseTests(unittest.TestCase):
    def test_typical_lines(self):
        i = ing.parse('1.5 lb chicken breast')
        self.assertEqual((i.qty, i.unit, i.name), (1.5, 'lb', 'chicken breast'))

    def test_pack_size_parenthetical_ignored(self):
        i = ing.parse('2 (14 oz) cans crushed tomatoes')
        self.assertEqual((i.qty, i.unit), (2.0, 'can'))
        self.assertEqual(i.name, 'crushed tomatoes')

    def test_countable_without_unit(self):
        i = ing.parse('3 bell peppers')
        self.assertEqual((i.qty, i.unit, i.key), (3.0, 'each', 'bell pepper'))

    def test_article_counts_as_one(self):
        i = ing.parse('a pinch of salt')
        self.assertEqual((i.qty, i.unit, i.name), (1.0, 'pinch', 'salt'))

    def test_unquantified(self):
        i = ing.parse('Salt and pepper to taste')
        self.assertIsNone(i.qty)
        self.assertEqual(i.name, 'Salt and pepper')

    def test_optional_flag_and_clean_name(self):
        i = ing.parse('2 tbsp olive oil (optional)')
        self.assertTrue(i.optional)
        self.assertEqual(i.name, 'olive oil')

    def test_raw_is_preserved(self):
        i = ing.parse('2-3 cloves garlic, minced')
        self.assertEqual(i.raw, '2-3 cloves garlic, minced')
        self.assertEqual(i.name, 'garlic')

    def test_bare_name(self):
        i = ing.parse('Kalamata olives')
        self.assertIsNone(i.qty)
        self.assertEqual(i.key, 'kalamata olive')


class CategoryTests(unittest.TestCase):
    def test_aisles(self):
        self.assertEqual(ing.guess_category('chicken breast'), 'meat')
        self.assertEqual(ing.guess_category('whole milk'), 'dairy')
        self.assertEqual(ing.guess_category('bell peppers'), 'produce')
        self.assertEqual(ing.guess_category('flour tortillas'), 'bakery')
        self.assertEqual(ing.guess_category('all-purpose flour'), 'pantry')
        self.assertEqual(ing.guess_category('frozen peas'), 'frozen')

    def test_overrides_beat_generic_keywords(self):
        # 'pepper' alone would read as produce.
        self.assertEqual(ing.guess_category('salt and pepper'), 'pantry')
        self.assertEqual(ing.guess_category('tomato paste'), 'pantry')
        self.assertEqual(ing.guess_category('ice cream'), 'frozen')

    def test_unknown_falls_back(self):
        self.assertEqual(ing.guess_category('xyzzy'), 'other')

    def test_every_category_is_a_configured_aisle(self):
        allowed = {'produce', 'dairy', 'meat', 'bakery', 'pantry', 'frozen', 'other'}
        for line in ('2 lb beef', 'milk', 'nothing recognisable here'):
            self.assertIn(ing.guess_category(line), allowed)


class AmountMathTests(unittest.TestCase):
    def test_add_same_unit(self):
        self.assertEqual(ing.add_amounts(1, 'cup', 2, 'cup'), (3.0, 'cup'))

    def test_add_converts(self):
        qty, unit = ing.add_amounts(1, 'lb', 8, 'oz')
        self.assertAlmostEqual(qty, 1.5, places=3)
        self.assertEqual(unit, 'lb')

    def test_add_incompatible_gives_up_on_the_number(self):
        # Rather than invent a total, fall back to unquantified.
        self.assertEqual(ing.add_amounts(1, 'cup', 1, 'lb'), (None, 'cup'))

    def test_add_with_missing_quantity(self):
        self.assertEqual(ing.add_amounts(None, '', 2, 'cup'), (2, 'cup'))
        self.assertEqual(ing.add_amounts(2, 'cup', None, ''), (2, 'cup'))

    def test_subtract_partial(self):
        remaining, unit, covered = ing.subtract_amounts(3, 'cup', 1, 'cup')
        self.assertEqual((remaining, unit, covered), (2.0, 'cup', False))

    def test_subtract_covers(self):
        remaining, _, covered = ing.subtract_amounts(2, 'cup', 4, 'cup')
        self.assertTrue(covered)
        self.assertEqual(remaining, 0.0)

    def test_subtract_across_units(self):
        remaining, unit, covered = ing.subtract_amounts(1, 'lb', 8, 'oz')
        self.assertAlmostEqual(remaining, 0.5, places=3)
        self.assertFalse(covered)

    def test_unquantified_need_is_covered_by_any_stock(self):
        _, _, covered = ing.subtract_amounts(None, '', 1, 'each')
        self.assertTrue(covered)

    def test_incompatible_units_do_not_cover(self):
        remaining, _, covered = ing.subtract_amounts(2, 'cup', 1, 'lb')
        self.assertFalse(covered)
        self.assertEqual(remaining, 2)


class AggregateTests(unittest.TestCase):
    def test_same_ingredient_across_recipes_combines(self):
        rows = ing.aggregate(ing.parse_all(['1 cup milk', '1/2 cup milk']))
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['qty'], 1.5)
        self.assertEqual(rows[0]['unit'], 'cup')

    def test_different_units_still_combine(self):
        rows = ing.aggregate(ing.parse_all(['1 lb beef', '8 oz beef']))
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['qty'], 1.5, places=3)

    def test_distinct_ingredients_stay_separate(self):
        rows = ing.aggregate(ing.parse_all(['1 cup milk', '2 eggs']))
        self.assertEqual(len(rows), 2)

    def test_plural_and_singular_merge(self):
        rows = ing.aggregate(ing.parse_all(['3 bell peppers', '1 bell pepper']))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['qty'], 4.0)

    def test_category_is_carried(self):
        rows = ing.aggregate(ing.parse_all(['1 lb chicken breast']))
        self.assertEqual(rows[0]['category'], 'meat')

    def test_sources_recorded(self):
        rows = ing.aggregate(ing.parse_all(['1 cup milk', '1 cup milk']))
        self.assertEqual(len(rows[0]['raw']), 2)


if __name__ == '__main__':
    unittest.main()
