"""
Tests for reading a recipe off a web page or out of pasted text.

The shapes here are not invented: every JSON-LD variant tested below was
taken from a real recipe site. Structured data is nominally a standard and
in practice is a dozen dialects, so the parser is mostly edge cases and the
tests have to be too.

Run from the backend/ directory:
    python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import recipe_import as ri  # noqa: E402


def page(*blocks):
    """A minimal HTML page wrapping some JSON-LD."""
    scripts = '\n'.join(
        f'<script type="application/ld+json">{b}</script>' for b in blocks)
    return f'<html><head><title>Page</title>{scripts}</head><body></body></html>'


class DurationTests(unittest.TestCase):
    def test_minutes_only(self):
        self.assertEqual(ri.parse_duration('PT45M'), 45)

    def test_hours_and_minutes(self):
        self.assertEqual(ri.parse_duration('PT1H30M'), 90)

    def test_hours_only(self):
        # The old importer matched only PT(\d+)M and so returned None here,
        # silently dropping the cook time on any recipe over an hour.
        self.assertEqual(ri.parse_duration('PT1H'), 60)

    def test_days(self):
        self.assertEqual(ri.parse_duration('P1DT2H'), 1560)

    def test_zero_day_prefix(self):
        self.assertEqual(ri.parse_duration('P0DT1H15M'), 75)

    def test_seconds_round(self):
        self.assertEqual(ri.parse_duration('PT90S'), 2)

    def test_prose_hours_and_minutes(self):
        self.assertEqual(ri.parse_duration('1 hr 30 mins'), 90)

    def test_prose_minutes(self):
        self.assertEqual(ri.parse_duration('20 minutes'), 20)

    def test_plain_number_is_minutes(self):
        self.assertEqual(ri.parse_duration(25), 25)

    def test_empty_and_junk(self):
        for value in (None, '', '   ', 'whenever', 'PT'):
            self.assertIsNone(ri.parse_duration(value), value)

    def test_zero_is_none_not_zero(self):
        # A zero cook time is noise, and None keeps it out of the UI.
        self.assertIsNone(ri.parse_duration('PT0M'))


class YieldAndImageTests(unittest.TestCase):
    def test_yield_from_prose(self):
        self.assertEqual(ri.first_int('4 servings'), 4)

    def test_yield_from_number(self):
        self.assertEqual(ri.first_int(6), 6)

    def test_yield_from_list(self):
        self.assertEqual(ri.first_int(['4', '4 servings']), 4)

    def test_yield_missing(self):
        self.assertIsNone(ri.first_int(None))
        self.assertIsNone(ri.first_int('a few'))

    def test_image_string(self):
        self.assertEqual(ri.first_url('http://x/a.jpg'), 'http://x/a.jpg')

    def test_image_list(self):
        self.assertEqual(ri.first_url(['http://x/a.jpg', 'http://x/b.jpg']),
                         'http://x/a.jpg')

    def test_image_object(self):
        self.assertEqual(ri.first_url({'@type': 'ImageObject',
                                       'url': 'http://x/c.jpg'}),
                         'http://x/c.jpg')

    def test_image_list_of_objects(self):
        self.assertEqual(
            ri.first_url([{'@type': 'ImageObject', 'contentUrl': 'http://x/d.jpg'}]),
            'http://x/d.jpg')

    def test_image_missing(self):
        self.assertEqual(ri.first_url(None), '')
        self.assertEqual(ri.first_url([]), '')


class JsonLdShapeTests(unittest.TestCase):
    """Where the Recipe object sits in the payload differs per site."""

    RECIPE = ('{"@context":"https://schema.org","@type":"Recipe",'
              '"name":"Fried Rice","recipeIngredient":["2 cups rice","1 egg"],'
              '"recipeInstructions":"Fry it."}')

    def test_bare_object(self):
        out = ri.parse_recipe_html(page(self.RECIPE))
        self.assertEqual(out['name'], 'Fried Rice')
        self.assertEqual(out['ingredients'], ['2 cups rice', '1 egg'])

    def test_array_of_objects(self):
        blob = f'[{{"@type":"WebSite","name":"Blog"}},{self.RECIPE}]'
        self.assertEqual(ri.parse_recipe_html(page(blob))['name'], 'Fried Rice')

    def test_graph(self):
        blob = ('{"@context":"https://schema.org","@graph":'
                f'[{{"@type":"WebPage","name":"x"}},{self.RECIPE}]}}')
        self.assertEqual(ri.parse_recipe_html(page(blob))['name'], 'Fried Rice')

    def test_type_as_list(self):
        blob = ('{"@type":["Recipe","NewsArticle"],"name":"Stew",'
                '"recipeIngredient":["1 onion"]}')
        self.assertEqual(ri.parse_recipe_html(page(blob))['name'], 'Stew')

    def test_second_script_used_when_first_has_no_recipe(self):
        self.assertEqual(
            ri.parse_recipe_html(page('{"@type":"Organization"}', self.RECIPE))['name'],
            'Fried Rice')

    def test_malformed_block_does_not_stop_the_search(self):
        # Trailing commas and concatenated objects are common; one bad script
        # must not hide a good one later in the page.
        self.assertEqual(
            ri.parse_recipe_html(page('{"broken":,}', self.RECIPE))['name'],
            'Fried Rice')

    def test_legacy_ingredients_key(self):
        blob = '{"@type":"Recipe","name":"Old","ingredients":["1 cup flour"]}'
        self.assertEqual(ri.parse_recipe_html(page(blob))['ingredients'],
                         ['1 cup flour'])


class InstructionShapeTests(unittest.TestCase):
    def steps(self, instructions_json):
        blob = ('{"@type":"Recipe","name":"X","recipeIngredient":["1 egg"],'
                f'"recipeInstructions":{instructions_json}}}')
        return ri.parse_recipe_html(page(blob))['instructions']

    def test_single_string(self):
        self.assertEqual(self.steps('"Mix well."'), '1. Mix well.')

    def test_list_of_strings(self):
        self.assertEqual(self.steps('["Chop.","Fry."]'), '1. Chop.\n\n2. Fry.')

    def test_howto_steps(self):
        out = self.steps('[{"@type":"HowToStep","text":"Chop."},'
                         '{"@type":"HowToStep","text":"Fry."}]')
        self.assertEqual(out, '1. Chop.\n\n2. Fry.')

    def test_howto_step_falls_back_to_name(self):
        self.assertEqual(self.steps('[{"@type":"HowToStep","name":"Rest it."}]'),
                         '1. Rest it.')

    def test_howto_sections_keep_their_headings(self):
        out = self.steps(
            '[{"@type":"HowToSection","name":"Dough",'
            '"itemListElement":[{"@type":"HowToStep","text":"Knead."}]},'
            '{"@type":"HowToSection","name":"Filling",'
            '"itemListElement":[{"@type":"HowToStep","text":"Dice."}]}]')
        self.assertIn('Dough:', out)
        self.assertIn('Filling:', out)
        # Headings must not consume step numbers, or the method reads wrong.
        self.assertIn('1. Knead.', out)
        self.assertIn('2. Dice.', out)

    def test_html_inside_a_step_is_stripped(self):
        self.assertEqual(self.steps('"<p>Mix <b>well</b>.</p>"'), '1. Mix well .')

    def test_entities_are_unescaped(self):
        self.assertEqual(self.steps('"Salt &amp; pepper"'), '1. Salt & pepper')

    def test_missing_instructions_is_empty_not_an_error(self):
        blob = '{"@type":"Recipe","name":"X","recipeIngredient":["1 egg"]}'
        self.assertEqual(ri.parse_recipe_html(page(blob))['instructions'], '')


class FieldMappingTests(unittest.TestCase):
    FULL = page(
        '{"@type":"Recipe","name":"Banana Bread",'
        '"description":"Moist &amp; easy.",'
        '"recipeIngredient":["3 bananas","2 cups flour"],'
        '"recipeInstructions":[{"@type":"HowToStep","text":"Bake."}],'
        '"prepTime":"PT15M","cookTime":"PT1H","recipeYield":"8 slices",'
        '"image":{"@type":"ImageObject","url":"http://x/b.jpg"},'
        '"recipeCategory":"Dessert","recipeCuisine":["American","American"]}')

    def setUp(self):
        self.out = ri.parse_recipe_html(self.FULL, 'http://x/banana')

    def test_scalar_fields(self):
        self.assertEqual(self.out['name'], 'Banana Bread')
        self.assertEqual(self.out['description'], 'Moist & easy.')
        self.assertEqual(self.out['prep_time'], 15)
        self.assertEqual(self.out['cook_time'], 60)
        self.assertEqual(self.out['servings'], 8)
        self.assertEqual(self.out['image_url'], 'http://x/b.jpg')

    def test_source_url_is_recorded(self):
        self.assertEqual(self.out['source_url'], 'http://x/banana')

    def test_tags_from_category_and_cuisine_deduplicated(self):
        self.assertEqual(self.out['tags'], ['Dessert', 'American'])

    def test_reports_which_strategy_worked(self):
        self.assertEqual(self.out['source'], 'json-ld')

    def test_shape_matches_what_the_recipe_endpoint_accepts(self):
        # POST /api/recipes reads exactly these keys; a rename here would
        # silently drop a field on save.
        for key in ('name', 'description', 'source_url', 'prep_time',
                    'cook_time', 'servings', 'ingredients', 'instructions',
                    'tags', 'image_url'):
            self.assertIn(key, self.out, key)


class MetaFallbackTests(unittest.TestCase):
    def test_name_and_image_come_from_meta_when_jsonld_omits_them(self):
        html = ('<html><head>'
                '<meta property="og:title" content="Pot Roast">'
                '<meta property="og:image" content="http://x/p.jpg">'
                '<meta name="description" content="Sunday dinner.">'
                '<script type="application/ld+json">'
                '{"@type":"Recipe","recipeIngredient":["1 roast"]}'
                '</script></head><body></body></html>')
        out = ri.parse_recipe_html(html)
        self.assertEqual(out['name'], 'Pot Roast')
        self.assertEqual(out['image_url'], 'http://x/p.jpg')
        self.assertEqual(out['description'], 'Sunday dinner.')

    def test_h1_used_when_there_is_no_og_title(self):
        html = ('<html><head><script type="application/ld+json">'
                '{"@type":"Recipe","recipeIngredient":["1 egg"]}'
                '</script></head><body><h1>Omelette</h1></body></html>')
        self.assertEqual(ri.parse_recipe_html(html)['name'], 'Omelette')


class MicrodataTests(unittest.TestCase):
    HTML = ('<html><body>'
            '<h1 itemprop="name">Microdata Soup</h1>'
            '<li itemprop="recipeIngredient">1 carrot</li>'
            '<li itemprop="recipeIngredient">2 cups stock</li>'
            '<div itemprop="recipeInstructions">Simmer.</div>'
            '<time itemprop="cookTime" datetime="PT30M">30 min</time>'
            '</body></html>')

    def test_used_when_there_is_no_jsonld(self):
        out = ri.parse_recipe_html(self.HTML)
        self.assertEqual(out['source'], 'microdata')
        self.assertEqual(out['ingredients'], ['1 carrot', '2 cups stock'])
        self.assertEqual(out['cook_time'], 30)

    def test_jsonld_wins_when_both_are_present(self):
        combined = self.HTML.replace(
            '<body>',
            '<body><script type="application/ld+json">'
            '{"@type":"Recipe","name":"JsonLd Soup",'
            '"recipeIngredient":["1 leek"]}</script>')
        out = ri.parse_recipe_html(combined)
        self.assertEqual(out['source'], 'json-ld')
        self.assertEqual(out['ingredients'], ['1 leek'])


class GuessworkTests(unittest.TestCase):
    def test_class_names_as_a_last_resort(self):
        html = ('<html><body><h1>Blog Chili</h1>'
                '<li class="wprm-recipe-ingredient">1 lb beef</li>'
                '<li class="wprm-recipe-instruction">Brown the beef.</li>'
                '</body></html>')
        out = ri.parse_recipe_html(html)
        self.assertEqual(out['source'], 'guesswork')
        self.assertEqual(out['ingredients'], ['1 lb beef'])
        self.assertEqual(out['name'], 'Blog Chili')


class NoRecipeTests(unittest.TestCase):
    def test_a_page_with_no_recipe_raises_rather_than_saving_an_empty_one(self):
        with self.assertRaises(ri.ImportFailed):
            ri.parse_recipe_html('<html><body><p>Hello</p></body></html>')

    def test_recipe_with_no_ingredients_is_not_accepted(self):
        blob = '{"@type":"Recipe","name":"Air","recipeInstructions":"Wait."}'
        with self.assertRaises(ri.ImportFailed):
            ri.parse_recipe_html(page(blob))

    def test_the_message_points_at_pasting(self):
        with self.assertRaises(ri.ImportFailed) as caught:
            ri.parse_recipe_html('<html></html>')
        self.assertIn('paste', str(caught.exception).lower())


class FakeResponse:
    def __init__(self, status_code, text=''):
        self.status_code = status_code
        self.text = text


class FakeSession:
    """Stands in for requests so no test touches the network."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


class FetchTests(unittest.TestCase):
    def test_success_returns_the_body(self):
        session = FakeSession(FakeResponse(200, '<html>hi</html>'))
        self.assertEqual(ri.fetch_html('http://x/', session=session),
                         '<html>hi</html>')

    def test_browser_headers_are_sent(self):
        # Several sites answer 403 to the default requests agent and 200 to a
        # browser one, so this is load-bearing rather than cosmetic.
        session = FakeSession(FakeResponse(200, 'ok'))
        ri.fetch_html('http://x/', session=session)
        headers = session.calls[0][1]['headers']
        self.assertIn('Chrome', headers['User-Agent'])
        self.assertIn('Accept-Language', headers)

    def test_redirects_are_followed(self):
        session = FakeSession(FakeResponse(200, 'ok'))
        ri.fetch_html('http://x/', session=session)
        self.assertTrue(session.calls[0][1]['allow_redirects'])

    def test_blocked_statuses_are_distinguished_from_plain_failure(self):
        for status in (401, 403, 406, 429, 451):
            session = FakeSession(FakeResponse(status))
            with self.assertRaises(ri.ImportBlocked, msg=status):
                ri.fetch_html('https://www.allrecipes.com/r/1', session=session)

    def test_blocked_message_names_the_site_and_offers_pasting(self):
        session = FakeSession(FakeResponse(403))
        with self.assertRaises(ri.ImportBlocked) as caught:
            ri.fetch_html('https://www.budgetbytes.com/x/', session=session)
        message = str(caught.exception)
        self.assertIn('budgetbytes.com', message)
        self.assertIn('paste', message.lower())

    def test_not_found_is_an_ordinary_failure(self):
        session = FakeSession(FakeResponse(404))
        with self.assertRaises(ri.ImportFailed):
            ri.fetch_html('http://x/', session=session)
        # A 404 is not a blocking site, so it must not suggest pasting as if
        # the page existed.
        self.assertNotIsInstance(ri.ImportFailed(), ri.ImportBlocked)

    def test_network_error_is_wrapped(self):
        session = FakeSession(error=OSError('dns go boom'))
        with self.assertRaises(ri.ImportFailed) as caught:
            ri.fetch_html('http://x/', session=session)
        self.assertIn('dns go boom', str(caught.exception))

    def test_import_from_url_fetches_then_parses(self):
        body = page('{"@type":"Recipe","name":"Soup",'
                    '"recipeIngredient":["1 onion"]}')
        session = FakeSession(FakeResponse(200, body))
        out = ri.import_from_url('http://x/soup', session=session)
        self.assertEqual(out['name'], 'Soup')
        self.assertEqual(out['source_url'], 'http://x/soup')


class PastedTextTests(unittest.TestCase):
    """The way through for sites that refuse to be fetched at all."""

    def test_headings_split_the_paste(self):
        out = ri.parse_recipe_text(
            'Ingredients\n'
            '2 cups flour\n'
            '1 tsp salt\n'
            'Instructions\n'
            'Mix the dry things together.\n'
            'Bake for 40 minutes until done.\n',
            name='Bread')
        self.assertEqual(out['name'], 'Bread')
        self.assertEqual(out['ingredients'], ['2 cups flour', '1 tsp salt'])
        self.assertEqual(out['instructions'],
                         '1. Mix the dry things together.\n\n'
                         '2. Bake for 40 minutes until done.')

    def test_numbered_steps_are_renumbered_not_doubled(self):
        out = ri.parse_recipe_text('Ingredients\n1 egg\n'
                                   'Directions\n1. Crack it.\n2. Fry it.\n')
        self.assertEqual(out['instructions'], '1. Crack it.\n\n2. Fry it.')

    def test_step_word_prefix_is_stripped(self):
        out = ri.parse_recipe_text('Ingredients\n1 egg\n'
                                   'Method\nStep 1. Crack it.\n')
        self.assertEqual(out['instructions'], '1. Crack it.')

    def test_notes_and_nutrition_are_dropped(self):
        out = ri.parse_recipe_text(
            'Ingredients\n1 egg\nInstructions\nFry it.\n'
            'Notes\nThis freezes well.\nNutrition\n200 calories\n')
        self.assertEqual(out['ingredients'], ['1 egg'])
        self.assertEqual(out['instructions'], '1. Fry it.')

    def test_without_headings_amounts_become_ingredients(self):
        out = ri.parse_recipe_text(
            '2 cups flour\n'
            '1 1/2 tsp salt\n'
            'Mix everything in a bowl and knead for ten minutes.\n')
        self.assertEqual(out['ingredients'], ['2 cups flour', '1 1/2 tsp salt'])
        self.assertIn('knead', out['instructions'])

    def test_vulgar_fractions_count_as_amounts(self):
        out = ri.parse_recipe_text('Ingredients\n¾ cup sugar\n')
        self.assertEqual(out['ingredients'], ['¾ cup sugar'])

    def test_a_title_above_the_headings_becomes_the_name(self):
        # Copying a recipe page gives you the title first, then the headings.
        # Judged on its own a title reads like a short unit-less ingredient,
        # so it used to land in the ingredient list.
        out = ri.parse_recipe_text(
            'Quick Beef Stir Fry\n'
            'Ingredients\n1/4 cup soy sauce\n3/4 pound beef sirloin\n'
            'Directions\nStep 1. Whisk the sauce.\n')
        self.assertEqual(out['name'], 'Quick Beef Stir Fry')
        self.assertEqual(out['ingredients'],
                         ['1/4 cup soy sauce', '3/4 pound beef sirloin'])

    def test_nutrition_facts_heading_is_dropped(self):
        # The heading had to stand alone to match, so "Nutrition Facts" and
        # "Chef's Notes" fell through and became extra steps.
        out = ri.parse_recipe_text(
            'Ingredients\n1 egg\nDirections\nFry it.\n'
            'Nutrition Facts\n280 calories\n')
        self.assertEqual(out['instructions'], '1. Fry it.')

    def test_notes_with_trailing_words_is_dropped(self):
        out = ri.parse_recipe_text(
            "Ingredients\n1 egg\nMethod\nFry it.\nRecipe Notes\nFreezes well.\n")
        self.assertEqual(out['instructions'], '1. Fry it.')

    def test_a_sentence_starting_with_tips_is_still_a_step(self):
        # "Tip" opens a noise heading but also plenty of real steps, so the
        # length and punctuation guard has to keep this one.
        out = ri.parse_recipe_text(
            'Ingredients\n1 egg\nMethod\n'
            'Tips for the pan: heat it until a drop of water skitters across.\n')
        self.assertIn('skitters', out['instructions'])

    def test_preamble_ingredients_keep_their_place(self):
        out = ri.parse_recipe_text(
            'Pancakes\n1 cup flour\nIngredients\n2 eggs\n')
        self.assertEqual(out['name'], 'Pancakes')
        self.assertEqual(out['ingredients'], ['1 cup flour', '2 eggs'])

    def test_a_leading_title_line_becomes_the_name(self):
        out = ri.parse_recipe_text('Quick Pancakes\n1 cup flour\n1 egg\n')
        self.assertEqual(out['name'], 'Quick Pancakes')
        self.assertEqual(out['ingredients'], ['1 cup flour', '1 egg'])

    def test_an_explicit_name_is_not_overwritten(self):
        out = ri.parse_recipe_text('1 cup flour\n', name='Given')
        self.assertEqual(out['name'], 'Given')
        self.assertEqual(out['ingredients'], ['1 cup flour'])

    def test_blank_lines_are_ignored(self):
        out = ri.parse_recipe_text('Ingredients\n\n1 egg\n\n\nInstructions\n\nFry.\n')
        self.assertEqual(out['ingredients'], ['1 egg'])

    def test_empty_paste_is_rejected(self):
        for value in ('', '   \n\n', None):
            with self.assertRaises(ri.ImportFailed):
                ri.parse_recipe_text(value)

    def test_prose_with_no_ingredients_is_rejected(self):
        with self.assertRaises(ri.ImportFailed):
            ri.parse_recipe_text(
                'This is a long story about my grandmother and her kitchen, '
                'with no actual amounts in it anywhere at all.\n'
                'It carries on for a second sentence as well.')

    def test_source_is_marked_pasted(self):
        out = ri.parse_recipe_text('Ingredients\n1 egg\n', url='http://x/')
        self.assertEqual(out['source'], 'pasted')
        self.assertEqual(out['source_url'], 'http://x/')

    def test_shape_matches_the_url_importer(self):
        pasted = ri.parse_recipe_text('Ingredients\n1 egg\n', name='A')
        fetched = ri.parse_recipe_html(
            page('{"@type":"Recipe","name":"A","recipeIngredient":["1 egg"]}'))
        self.assertEqual(set(pasted), set(fetched))



CHATGPT_PASTE = """You said:
can you give me a weeknight chicken thing the kids will eat

ChatGPT said:
Absolutely! Here's a super easy one that's always a hit

**Honey Garlic Chicken Thighs**

Prep time: 10 minutes
Cook time: 25 minutes
Serves: 4

These come out sticky and sweet, and they only need one pan.

### Ingredients

- 8 boneless skinless chicken thighs
- 1/3 cup honey
- 3 tbsp soy sauce
- Salt and pepper

### Instructions

1. Pat the chicken dry and season both sides.
2. Sear the thighs about 5 minutes per side.
3. Pour the sauce over and simmer until it thickens.

**Tips**
- Swap the thighs for drumsticks.

Let me know if you want a sheet-pan version!
"""


class ChatTranscriptTests(unittest.TestCase):
    """A recipe copied out of an assistant is a conversation, not a page."""

    def test_a_chatgpt_paste_comes_out_standardised(self):
        out = ri.parse_recipe_chat(CHATGPT_PASTE)
        self.assertEqual(out['name'], 'Honey Garlic Chicken Thighs')
        self.assertEqual(out['prep_time'], 10)
        self.assertEqual(out['cook_time'], 25)
        self.assertEqual(out['servings'], 4)
        self.assertEqual(out['source'], 'chat')
        self.assertIn('sticky and sweet', out['description'])

    def test_a_markdown_heading_title_is_used_as_the_name(self):
        # Assistants put the dish name in bold or as a heading depending
        # on the day. A heading used to fall through into the description.
        chat = "\n".join([
            "Claude said:",
            "## Skillet Beef and Rice",
            "Makes: 6 servings",
            "One pan, and it reheats well.",
            "**Ingredients**",
            "* 1 lb ground beef",
            "* 1 cup rice",
            "**Instructions**",
            "1. Brown the beef.",
        ])
        out = ri.parse_recipe_chat(chat)
        self.assertEqual(out['name'], 'Skillet Beef and Rice')
        self.assertNotIn('Skillet Beef and Rice', out['description'])
        self.assertEqual(out['servings'], 6)
        self.assertEqual(out['ingredients'], ['1 lb ground beef', '1 cup rice'])
        self.assertIn('Brown the beef', out['instructions'])

    def test_the_question_that_was_asked_is_not_a_step(self):
        out = ri.parse_recipe_chat(CHATGPT_PASTE)
        self.assertNotIn('kids will eat', out['instructions'])
        self.assertNotIn('You said', out['name'])
        self.assertNotIn('You said', out['instructions'])

    def test_sign_offs_and_tips_are_dropped(self):
        out = ri.parse_recipe_chat(CHATGPT_PASTE)
        self.assertNotIn('sheet-pan version', out['instructions'])
        self.assertNotIn('drumsticks', out['instructions'])
        self.assertNotIn('Absolutely', out['instructions'])

    def test_a_sign_off_after_the_last_step_is_not_a_step(self):
        # The common shape: the offer comes after the instructions, so a
        # rule that only looked before the first heading never caught it.
        chat = "\n".join([
            "ChatGPT said:",
            "**Garlic Butter Shrimp**",
            "### Ingredients",
            "- 1 lb shrimp",
            "### Instructions",
            "1. Melt the butter.",
            "2. Add the shrimp.",
            "",
            "Let me know if you want it spicy!",
        ])
        out = ri.parse_recipe_chat(chat)
        self.assertNotIn('spicy', out['instructions'])
        self.assertIn('Melt the butter', out['instructions'])
        self.assertIn('Add the shrimp', out['instructions'])

    def test_a_step_opening_like_a_lead_in_is_kept(self):
        # "Try this" only reads as throat-clearing before the recipe; once
        # inside the steps it is an instruction and must survive.
        chat = "\n".join([
            "**Pan Toast**",
            "Ingredients",
            "2 slices bread",
            "Instructions",
            "1. Butter both sides.",
            "2. Try this with the heat low so it does not scorch.",
        ])
        out = ri.parse_recipe_chat(chat)
        self.assertIn('heat low', out['instructions'])

    def test_markdown_is_flattened_off_the_ingredients(self):
        out = ri.parse_recipe_chat(CHATGPT_PASTE)
        self.assertEqual(out['ingredients'][0], '8 boneless skinless chicken thighs')
        for line in out['ingredients']:
            self.assertFalse(line.startswith('-'), line)
            self.assertNotIn('**', line)

    def test_numbered_steps_survive_bullet_stripping(self):
        # "1. Pat the chicken dry" must not lose its text to the bullet regex.
        out = ri.parse_recipe_chat(CHATGPT_PASTE)
        self.assertIn('Pat the chicken dry', out['instructions'])
        self.assertIn('simmer until it thickens', out['instructions'])

    def test_a_chat_with_no_headings_still_parses(self):
        out = ri.parse_recipe_chat(
            "Claude said:\n"
            "**Cinnamon Toast**\n"
            "2 slices bread\n"
            "1 tbsp butter\n"
            "Toast the bread, then butter it.\n")
        self.assertEqual(out['name'], 'Cinnamon Toast')
        self.assertIn('2 slices bread', out['ingredients'])
        self.assertIn('Toast the bread', out['instructions'])

    def test_total_time_is_used_when_prep_and_cook_are_absent(self):
        out = ri.parse_recipe_chat(
            "**Toast**\nTotal time: 1 hr 5 mins\nIngredients\n2 slices bread\n"
            "Instructions\nToast it.\n")
        self.assertEqual(out['cook_time'], 65)

    def test_an_empty_or_recipeless_chat_is_refused(self):
        for value in ('', '   ', 'You said:\nhello\n'):
            with self.assertRaises(ri.ImportFailed):
                ri.parse_recipe_chat(value)


class ChatDetectionTests(unittest.TestCase):
    """Guessing wrong sends an ordinary paste down the chattier path."""

    def test_assistant_pastes_are_detected(self):
        self.assertTrue(ri.looks_like_chat(CHATGPT_PASTE))
        self.assertTrue(ri.looks_like_chat('## Ingredients\n1 egg\n'))
        self.assertTrue(ri.looks_like_chat('**Pancakes**\n1 egg\n'))

    def test_an_ordinary_recipe_paste_is_not_mistaken_for_a_chat(self):
        self.assertFalse(ri.looks_like_chat(
            'Quick Pancakes\nIngredients\n- 1 cup flour\n- 1 egg\n'
            'Instructions\nMix and fry.\n'))
        self.assertFalse(ri.looks_like_chat(''))
        self.assertFalse(ri.looks_like_chat('1 egg\n2 cups flour\n'))


class StripMarkdownTests(unittest.TestCase):
    def test_inline_markup_is_removed(self):
        self.assertEqual(ri.strip_markdown('### Ingredients'), 'Ingredients')
        self.assertEqual(ri.strip_markdown('- 1 cup flour'), '1 cup flour')
        self.assertEqual(ri.strip_markdown('**Bold Title**'), 'Bold Title')
        self.assertEqual(ri.strip_markdown('a [link](http://x) here'), 'a link here')
        self.assertEqual(ri.strip_markdown('`code`'), 'code')
        self.assertEqual(ri.strip_markdown('---'), '')

    def test_a_numbered_step_keeps_its_number_for_the_step_parser(self):
        self.assertEqual(ri.strip_markdown('1. Pat the chicken dry'),
                         '1. Pat the chicken dry')

if __name__ == '__main__':
    unittest.main()
