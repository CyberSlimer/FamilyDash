"""
Tests for the meals <-> grocery <-> pantry loop.

Run from the backend/ directory:
    python -m unittest discover -s tests -v
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point the app at throwaway storage BEFORE importing it.
_tmp = tempfile.mkdtemp()
os.environ['CALENDARS_FILE'] = os.path.join(_tmp, 'calendars.json')
os.environ['DASHBOARD_DB'] = os.path.join(_tmp, 'test.db')
os.environ['DASHBOARD_PHOTOS'] = os.path.join(_tmp, 'photos')

import app as dashboard  # noqa: E402


def tearDownModule():
    shutil.rmtree(_tmp, ignore_errors=True)


class InventoryTestCase(unittest.TestCase):
    """Each test starts from an empty database."""

    def setUp(self):
        self.ctx = dashboard.app.app_context()
        self.ctx.push()
        dashboard.db.drop_all()
        dashboard.db.create_all()
        self.client = dashboard.app.test_client()

    def tearDown(self):
        dashboard.db.session.remove()
        self.ctx.pop()

    # -- helpers ----------------------------------------------------------
    def add_recipe(self, name, ingredients, servings=4):
        res = self.client.post('/api/recipes', json={
            'name': name, 'ingredients': ingredients, 'servings': servings})
        return res.get_json()['id']

    def plan(self, recipe_id, date='2026-09-21', meal_type='dinner', **kw):
        res = self.client.post('/api/meals', json={
            'date': date, 'meal_type': meal_type, 'recipe_id': recipe_id, **kw})
        return res.get_json()['id']

    def stock(self, name, quantity, location='pantry', **kw):
        res = self.client.post('/api/pantry', json={
            'name': name, 'quantity': quantity, 'location': location, **kw})
        return res.get_json()['id']

    def generate(self, **kw):
        body = {'start_date': '2026-09-01', 'end_date': '2026-10-01'}
        body.update(kw)
        return self.client.post('/api/grocery/generate', json=body).get_json()

    def grocery(self):
        return self.client.get('/api/grocery').get_json()

    def pantry(self):
        return self.client.get('/api/pantry').get_json()

    def by_name(self, rows, name):
        for row in rows:
            if row['name'].lower() == name.lower():
                return row
        return None


class GenerateTests(InventoryTestCase):
    def test_ingredients_become_grocery_rows(self):
        self.plan(self.add_recipe('Fajitas', ['1.5 lb chicken breast', '3 bell peppers']))
        result = self.generate()
        self.assertEqual(len(result['added']), 2)
        names = {r['name'] for r in self.grocery()}
        self.assertEqual(names, {'chicken breast', 'bell peppers'})

    def test_quantity_is_the_amount_not_a_recipe_count(self):
        # The old behaviour put "2" (how many recipes mentioned it) in quantity.
        self.plan(self.add_recipe('A', ['1.5 lb chicken breast']))
        self.generate()
        row = self.by_name(self.grocery(), 'chicken breast')
        self.assertEqual(row['quantity'], '1 1/2 lb')
        self.assertAlmostEqual(row['qty'], 1.5)
        self.assertEqual(row['unit'], 'lb')

    def test_same_ingredient_across_recipes_is_summed(self):
        self.plan(self.add_recipe('A', ['1.5 lb chicken breast']), date='2026-09-21')
        self.plan(self.add_recipe('B', ['1 lb chicken breast']), date='2026-09-22')
        self.generate()
        rows = [r for r in self.grocery() if r['match_key'] == 'chicken breast']
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['qty'], 2.5)

    def test_units_are_converted_when_summing(self):
        self.plan(self.add_recipe('A', ['1 lb beef']), date='2026-09-21')
        self.plan(self.add_recipe('B', ['8 oz beef']), date='2026-09-22')
        self.generate()
        row = self.by_name(self.grocery(), 'beef')
        self.assertAlmostEqual(row['qty'], 1.5, places=2)
        self.assertEqual(row['unit'], 'lb')

    def test_pantry_stock_is_subtracted(self):
        self.stock('bell peppers', '2')
        self.plan(self.add_recipe('A', ['5 bell peppers']))
        self.generate()
        row = self.by_name(self.grocery(), 'bell peppers')
        self.assertEqual(row['qty'], 3.0)

    def test_fully_stocked_ingredient_is_skipped(self):
        self.stock('rice', '5 lb')
        self.plan(self.add_recipe('A', ['1 lb rice']))
        result = self.generate()
        self.assertEqual([s['name'] for s in result['skipped']], ['rice'])
        self.assertIsNone(self.by_name(self.grocery(), 'rice'))

    def test_use_pantry_false_ignores_stock(self):
        self.stock('rice', '5 lb')
        self.plan(self.add_recipe('A', ['1 lb rice']))
        self.generate(use_pantry=False)
        self.assertIsNotNone(self.by_name(self.grocery(), 'rice'))

    def test_regenerating_merges_instead_of_duplicating(self):
        self.plan(self.add_recipe('A', ['2 cups milk']))
        self.generate()
        result = self.generate()
        rows = [r for r in self.grocery() if r['match_key'] == 'milk']
        self.assertEqual(len(rows), 1, 'a second generate must not duplicate the row')
        self.assertEqual(len(result['added']), 0)
        self.assertEqual(len(result['merged']), 1)

    def test_generated_rows_get_a_real_category(self):
        self.plan(self.add_recipe('A', ['1 lb chicken breast', '2 cups milk', '1 loaf bread']))
        self.generate()
        rows = {r['name']: r['category'] for r in self.grocery()}
        self.assertEqual(rows['chicken breast'], 'meat')
        self.assertEqual(rows['milk'], 'dairy')
        self.assertEqual(rows['bread'], 'bakery')
        self.assertNotIn('generated', rows.values())

    def test_generated_rows_link_back_to_their_recipe(self):
        rid = self.add_recipe('Fajitas', ['1.5 lb chicken breast'])
        self.plan(rid)
        self.generate()
        row = self.by_name(self.grocery(), 'chicken breast')
        self.assertEqual(row['recipe_id'], rid)
        self.assertEqual(row['recipe_name'], 'Fajitas')

    def test_optional_ingredients_can_be_excluded(self):
        self.plan(self.add_recipe('A', ['1 lb beef', '2 tbsp parsley (optional)']))
        self.generate(include_optional=False)
        self.assertIsNone(self.by_name(self.grocery(), 'parsley'))

    def test_meals_without_recipes_are_ignored(self):
        self.client.post('/api/meals', json={
            'date': '2026-09-21', 'meal_type': 'dinner', 'custom_meal': 'Leftovers'})
        result = self.generate()
        self.assertEqual(result['added'], [])

    def test_servings_override_scales_quantities(self):
        rid = self.add_recipe('A', ['1 lb beef'], servings=4)
        self.plan(rid, servings=8)
        self.generate()
        row = self.by_name(self.grocery(), 'beef')
        self.assertAlmostEqual(row['qty'], 2.0)

    def test_grocery_rows_report_pantry_coverage(self):
        self.stock('milk', '1 cup')
        self.plan(self.add_recipe('A', ['3 cups milk']))
        self.generate()
        row = self.by_name(self.grocery(), 'milk')
        self.assertTrue(row['in_pantry'])
        self.assertEqual(row['pantry_amount'], '1 cup')


class RestockTests(InventoryTestCase):
    def test_checked_items_move_into_the_pantry(self):
        self.client.post('/api/grocery', json={'name': 'milk', 'quantity': '2 cup'})
        row = self.grocery()[0]
        self.client.put(f"/api/grocery/{row['id']}", json={'checked': True})
        result = self.client.post('/api/grocery/clear-checked', json={}).get_json()

        self.assertEqual(result['cleared'], 1)
        self.assertEqual(self.grocery(), [])
        pantry_row = self.by_name(self.pantry(), 'milk')
        self.assertIsNotNone(pantry_row)
        self.assertEqual(pantry_row['quantity'], '2 cups')

    def test_restock_merges_with_existing_stock(self):
        self.stock('milk', '1 cup')
        self.client.post('/api/grocery', json={'name': 'milk', 'quantity': '2 cup'})
        row = self.grocery()[0]
        self.client.put(f"/api/grocery/{row['id']}", json={'checked': True})
        self.client.post('/api/grocery/clear-checked', json={})

        rows = [r for r in self.pantry() if r['match_key'] == 'milk']
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['qty'], 3.0)

    def test_unchecked_items_are_left_alone(self):
        self.client.post('/api/grocery', json={'name': 'milk', 'quantity': '2 cup'})
        self.client.post('/api/grocery/clear-checked', json={})
        self.assertEqual(len(self.grocery()), 1)
        self.assertEqual(self.pantry(), [])

    def test_to_pantry_false_just_clears(self):
        self.client.post('/api/grocery', json={'name': 'milk', 'quantity': '2 cup'})
        row = self.grocery()[0]
        self.client.put(f"/api/grocery/{row['id']}", json={'checked': True})
        self.client.post('/api/grocery/clear-checked', json={'to_pantry': False})
        self.assertEqual(self.grocery(), [])
        self.assertEqual(self.pantry(), [])

    def test_restock_location_is_honoured(self):
        self.client.post('/api/grocery', json={'name': 'milk', 'quantity': '1 gallon'})
        row = self.grocery()[0]
        self.client.put(f"/api/grocery/{row['id']}", json={'checked': True})
        self.client.post('/api/grocery/clear-checked', json={'location': 'fridge'})
        self.assertEqual(self.by_name(self.pantry(), 'milk')['location'], 'fridge')

    def test_pantry_item_can_be_put_back_on_the_list(self):
        pid = self.stock('olive oil', '1 bottle')
        result = self.client.post(f'/api/pantry/{pid}/to-grocery', json={}).get_json()
        self.assertTrue(result['created'])
        self.assertIsNotNone(self.by_name(self.grocery(), 'olive oil'))

    def test_to_grocery_does_not_duplicate(self):
        pid = self.stock('olive oil', '1 bottle')
        self.client.post(f'/api/pantry/{pid}/to-grocery', json={})
        result = self.client.post(f'/api/pantry/{pid}/to-grocery', json={}).get_json()
        self.assertFalse(result['created'])
        self.assertEqual(len([r for r in self.grocery() if r['match_key'] == 'olive oil']), 1)


class CookTests(InventoryTestCase):
    def test_cooking_deducts_from_the_pantry(self):
        self.stock('chicken breast', '3 lb')
        mid = self.plan(self.add_recipe('A', ['1 lb chicken breast']))
        result = self.client.post(f'/api/meals/{mid}/cook', json={}).get_json()

        self.assertEqual(result['consumed'], [{'name': 'chicken breast', 'used': '1 lb'}])
        self.assertAlmostEqual(self.by_name(self.pantry(), 'chicken breast')['qty'], 2.0)

    def test_stock_that_runs_out_is_removed(self):
        self.stock('chicken breast', '1 lb')
        mid = self.plan(self.add_recipe('A', ['1 lb chicken breast']))
        self.client.post(f'/api/meals/{mid}/cook', json={})
        self.assertEqual(self.pantry(), [])

    def test_shortfall_is_reported_not_negative(self):
        self.stock('chicken breast', '0.5 lb')
        mid = self.plan(self.add_recipe('A', ['2 lb chicken breast']))
        result = self.client.post(f'/api/meals/{mid}/cook', json={}).get_json()
        self.assertEqual(len(result['short']), 1)
        self.assertEqual(result['short'][0]['name'], 'chicken breast')
        for row in self.pantry():
            self.assertGreaterEqual(row['qty'] or 0, 0)

    def test_shortfall_can_go_on_the_grocery_list(self):
        mid = self.plan(self.add_recipe('A', ['2 lb chicken breast']))
        self.client.post(f'/api/meals/{mid}/cook', json={'add_missing_to_grocery': True})
        self.assertIsNotNone(self.by_name(self.grocery(), 'chicken breast'))

    def test_cooking_twice_is_refused(self):
        self.stock('chicken breast', '5 lb')
        mid = self.plan(self.add_recipe('A', ['1 lb chicken breast']))
        self.client.post(f'/api/meals/{mid}/cook', json={})
        second = self.client.post(f'/api/meals/{mid}/cook', json={})
        self.assertEqual(second.status_code, 409)
        self.assertAlmostEqual(self.by_name(self.pantry(), 'chicken breast')['qty'], 4.0)

    def test_force_allows_a_second_deduction(self):
        self.stock('chicken breast', '5 lb')
        mid = self.plan(self.add_recipe('A', ['1 lb chicken breast']))
        self.client.post(f'/api/meals/{mid}/cook', json={})
        self.client.post(f'/api/meals/{mid}/cook', json={'force': True})
        self.assertAlmostEqual(self.by_name(self.pantry(), 'chicken breast')['qty'], 3.0)

    def test_uncook_clears_the_flag(self):
        mid = self.plan(self.add_recipe('A', ['1 lb beef']))
        self.client.post(f'/api/meals/{mid}/cook', json={})
        self.client.post(f'/api/meals/{mid}/uncook', json={})
        meals = self.client.get('/api/meals').get_json()
        self.assertIsNone(meals[0]['cooked_at'])

    def test_oldest_expiry_is_used_first(self):
        self.stock('milk', '1 cup', expiration_date='2026-09-20')
        self.stock('milk', '1 cup', expiration_date='2026-12-31')
        mid = self.plan(self.add_recipe('A', ['1 cup milk']))
        self.client.post(f'/api/meals/{mid}/cook', json={})
        rows = [r for r in self.pantry() if r['match_key'] == 'milk']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['expiration_date'], '2026-12-31')

    def test_custom_meal_cannot_be_cooked(self):
        res = self.client.post('/api/meals', json={
            'date': '2026-09-21', 'meal_type': 'dinner', 'custom_meal': 'Takeout'})
        mid = res.get_json()['id']
        self.assertEqual(self.client.post(f'/api/meals/{mid}/cook', json={}).status_code, 400)


class AvailabilityTests(InventoryTestCase):
    def test_reports_what_is_on_hand(self):
        self.stock('chicken breast', '3 lb')
        mid = self.plan(self.add_recipe('A', ['1 lb chicken breast', '2 cups rice']))
        data = self.client.get(f'/api/meals/{mid}/availability').get_json()
        self.assertEqual(data['total'], 2)
        self.assertEqual(data['have'], 1)
        self.assertEqual([m['name'] for m in data['missing']], ['rice'])

    def test_mixed_units_in_the_pantry_still_count(self):
        # An unopened 16 oz bottle plus 4 tbsp left over covers a 2 tbsp need.
        self.stock('olive oil', '4 tbsp')
        self.stock('olive oil', '16 oz')
        mid = self.plan(self.add_recipe('A', ['2 tbsp olive oil']))
        data = self.client.get(f'/api/meals/{mid}/availability').get_json()
        self.assertEqual(data['have'], 1, data['ingredients'])

    def test_meal_list_can_include_coverage(self):
        self.stock('beef', '5 lb')
        self.plan(self.add_recipe('A', ['1 lb beef', '2 cups rice']))
        meals = self.client.get('/api/meals?with_availability=1').get_json()
        self.assertEqual(meals[0]['have'], 1)
        self.assertEqual(meals[0]['total'], 2)

    def test_coverage_is_omitted_unless_asked(self):
        self.plan(self.add_recipe('A', ['1 lb beef']))
        self.assertNotIn('have', self.client.get('/api/meals').get_json()[0])


class RowNormalizationTests(InventoryTestCase):
    def test_amount_typed_into_the_name_is_lifted_out(self):
        self.client.post('/api/grocery', json={'name': '2 lb ground beef'})
        row = self.grocery()[0]
        self.assertEqual(row['name'], 'ground beef')
        self.assertEqual(row['quantity'], '2 lb')

    def test_display_text_follows_the_parsed_amount(self):
        # Rows written before a formatting change must not keep stale text.
        self.client.post('/api/grocery', json={'name': 'milk', 'quantity': '2 cup'})
        row_id = self.grocery()[0]['id']
        stored = dashboard.db.session.get(dashboard.GroceryItem, row_id)
        stored.quantity = '2 cup'          # how an older version wrote it
        dashboard.db.session.commit()
        self.assertEqual(self.grocery()[0]['quantity'], '2 cups')

    def test_unparseable_quantity_is_kept_as_text(self):
        self.client.post('/api/grocery', json={'name': 'napkins', 'quantity': 'a few'})
        row = self.grocery()[0]
        self.assertEqual(row['quantity'], 'a few')
        self.assertIsNone(row['qty'])

    def test_editing_keeps_the_match_key_in_step(self):
        self.client.post('/api/grocery', json={'name': 'milk'})
        row = self.grocery()[0]
        self.client.put(f"/api/grocery/{row['id']}", json={'name': 'orange juice'})
        self.assertEqual(self.grocery()[0]['match_key'], 'orange juice')

    def test_descriptors_do_not_split_a_match(self):
        # 'whole milk' in the pantry should still cover a recipe's 'milk'.
        self.stock('whole milk', '4 cup')
        mid = self.plan(self.add_recipe('A', ['1 cup milk']))
        data = self.client.get(f'/api/meals/{mid}/availability').get_json()
        self.assertEqual(data['have'], 1)

    def test_checking_an_item_does_not_disturb_its_amount(self):
        self.client.post('/api/grocery', json={'name': 'milk', 'quantity': '2 cup'})
        row = self.grocery()[0]
        self.client.put(f"/api/grocery/{row['id']}", json={'checked': True})
        self.assertEqual(self.grocery()[0]['quantity'], '2 cups')


class MigrationTests(InventoryTestCase):
    def test_adds_missing_columns_to_an_old_database(self):
        from sqlalchemy import inspect, text
        # Simulate a pre-upgrade install: drop the new columns.
        dashboard.db.session.remove()
        with dashboard.db.engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS grocery_item'))
            conn.execute(text('CREATE TABLE grocery_item ('
                              'id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL, '
                              'quantity VARCHAR(50), category VARCHAR(50), '
                              'checked BOOLEAN, recipe_id INTEGER, '
                              'created_at DATETIME, list_id INTEGER)'))
            conn.execute(text("INSERT INTO grocery_item (name, quantity, checked, list_id) "
                              "VALUES ('2 lb ground beef', '', 0, 1)"))

        dashboard._migrate_schema()
        columns = {c['name'] for c in inspect(dashboard.db.engine).get_columns('grocery_item')}
        self.assertTrue({'qty', 'unit', 'match_key'} <= columns)

    def test_backfill_gives_old_rows_a_match_key(self):
        from sqlalchemy import text
        dashboard.db.session.remove()
        with dashboard.db.engine.begin() as conn:
            conn.execute(text("INSERT INTO grocery_item (name, quantity, checked, list_id) "
                              "VALUES ('2 lb ground beef', '', 0, 1)"))
        dashboard._backfill_match_keys()
        row = self.grocery()[0]
        self.assertEqual(row['match_key'], 'ground beef')
        self.assertEqual(row['quantity'], '2 lb')


if __name__ == '__main__':
    unittest.main()
