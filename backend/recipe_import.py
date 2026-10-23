#!/usr/bin/env python3
"""
Turn a recipe web page - or text pasted out of one - into recipe fields.

The original importer looked for `itemprop` attributes and CSS classes named
"ingredient". Almost no modern recipe site marks up its page that way any
more: they publish a schema.org Recipe as JSON-LD in a <script> tag, because
that is what Google reads for search results. Every site surveyed that could
be fetched at all had JSON-LD, and none of them had usable class names, so
JSON-LD is tried first and the old guesswork is kept only as a last resort.

The other half of the problem is not parsing but fetching: a good number of
the big recipe sites (allrecipes, budgetbytes, seriouseats, simplyrecipes)
answer 403 to anything that is not a real browser, whatever headers are sent.
No server-side scraper gets past that, so `fetch_html` raises `ImportBlocked`
for those specifically, which lets the caller tell the user to paste the
recipe instead of showing a generic failure.

Nothing here touches the database or Flask, so it can be unit-tested on its
own.
"""

import html as html_module
import json
import re

from bs4 import BeautifulSoup

# A plain requests User-Agent is refused by most recipe sites, so present a
# current desktop Chrome along with the headers a browser would really send.
# This is not enough for the sites behind bot protection, but it is the
# difference between working and not for the ones that only check the agent.
BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/140.0.0.0 Safari/537.36'),
    'Accept': ('text/html,application/xhtml+xml,application/xml;q=0.9,'
               'image/avif,image/webp,*/*;q=0.8'),
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
}

FETCH_TIMEOUT = 15

# Status codes that mean "this site refuses automated clients", as opposed to
# a page that is merely missing or broken.
BLOCKED_STATUSES = (401, 403, 406, 429, 451)


class ImportError_(Exception):
    """Base for import failures that carry a message fit for the user."""


class ImportBlocked(ImportError_):
    """The site refused us. Pasting the recipe is the only way through."""


class ImportFailed(ImportError_):
    """Fetched something, but it could not be read as a recipe."""


# ============================================================================
# SMALL HELPERS
# ============================================================================

_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'[ \t ]+')


def clean_text(value):
    """Flatten a JSON-LD string: strip tags, unescape entities, tidy space."""
    if value is None:
        return ''
    if not isinstance(value, str):
        value = str(value)
    value = _TAG_RE.sub(' ', value)
    value = html_module.unescape(value)
    value = _WS_RE.sub(' ', value)
    return value.strip()


# PT1H30M, PT45M, P0DT1H15M - hours and minutes are all the Recipe model has
# a use for, but days appear on slow-cooker and curing recipes so they count
# too. The previous code only matched PT(\d+)M, which silently returned None
# for every recipe written as "PT1H".
_DURATION_RE = re.compile(
    r'^P'
    r'(?:(?P<days>\d+(?:\.\d+)?)D)?'
    r'(?:T'
    r'(?:(?P<hours>\d+(?:\.\d+)?)H)?'
    r'(?:(?P<minutes>\d+(?:\.\d+)?)M)?'
    r'(?:(?P<seconds>\d+(?:\.\d+)?)S)?'
    r')?$',
    re.I)


def parse_duration(value):
    """ISO-8601 duration to whole minutes, or None if it is not one."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # A few sites write plain minutes instead of a duration.
        return int(value) if value > 0 else None
    text = str(value).strip()
    if not text:
        return None

    match = _DURATION_RE.match(text)
    if match and any(match.group(g) for g in ('days', 'hours', 'minutes', 'seconds')):
        total = (float(match.group('days') or 0) * 1440
                 + float(match.group('hours') or 0) * 60
                 + float(match.group('minutes') or 0)
                 + float(match.group('seconds') or 0) / 60)
        return int(round(total)) or None

    # Fall back to prose: "1 hr 30 mins", "45 minutes".
    hours = re.search(r'(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)\b', text, re.I)
    mins = re.search(r'(\d+(?:\.\d+)?)\s*(?:m|min|mins|minute|minutes)\b', text, re.I)
    if hours or mins:
        total = (float(hours.group(1)) * 60 if hours else 0) + \
                (float(mins.group(1)) if mins else 0)
        return int(round(total)) or None
    return None


def first_int(value):
    """The first whole number in a yield like "4 servings", a list, or 4."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) or None
    if isinstance(value, list):
        for item in value:
            found = first_int(item)
            if found:
                return found
        return None
    match = re.search(r'\d+', str(value))
    return int(match.group(0)) if match else None


def first_url(value):
    """An `image` can be a string, a list, or an ImageObject - or a list of them."""
    if not value:
        return ''
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return first_url(value.get('url') or value.get('contentUrl'))
    if isinstance(value, list):
        for item in value:
            found = first_url(item)
            if found:
                return found
    return ''


def as_list(value):
    """JSON-LD fields are singular or plural with no warning."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


# ============================================================================
# JSON-LD
# ============================================================================

def _walk(node, depth=0):
    """Every dict nested anywhere inside a decoded JSON document."""
    if depth > 12:
        return
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value, depth + 1)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item, depth + 1)


def _is_recipe(node):
    """`@type` may be "Recipe" or a list that includes it."""
    types = as_list(node.get('@type'))
    return any(isinstance(t, str) and t.lower() == 'recipe' for t in types)


def find_recipe_node(data):
    """
    The Recipe object inside a JSON-LD payload.

    Sites wrap it in every shape imaginable: bare object, array of objects,
    or an @graph listing the page, the author, the breadcrumbs and the recipe
    together. Walking the whole tree is simpler than handling each shape.
    """
    for node in _walk(data):
        if _is_recipe(node):
            return node
    return None


def _instruction_lines(value, depth=0):
    """
    `recipeInstructions` flattened to a list of step strings.

    Shapes seen in the wild: a single paragraph, a list of strings, a list of
    HowToStep objects, and HowToSection objects that each hold their own list
    of steps (a recipe with "For the dough" / "For the filling").
    """
    lines = []
    if depth > 6 or value is None:
        return lines

    if isinstance(value, str):
        text = clean_text(value)
        if text:
            lines.append(text)
        return lines

    if isinstance(value, list):
        for item in value:
            lines.extend(_instruction_lines(item, depth + 1))
        return lines

    if isinstance(value, dict):
        types = [t.lower() for t in as_list(value.get('@type')) if isinstance(t, str)]
        if 'howtosection' in types:
            name = clean_text(value.get('name'))
            steps = _instruction_lines(
                value.get('itemListElement') or value.get('steps'), depth + 1)
            if steps:
                if name:
                    lines.append('## ' + name)
                lines.extend(steps)
            return lines
        text = clean_text(value.get('text') or value.get('name'))
        if text:
            lines.append(text)
        return lines

    return lines


def _number_steps(lines):
    """
    Render step lines the way the recipe screen expects: "1. ...".

    Section headers (added by `_instruction_lines`) are passed through as
    plain text and do not consume a step number.
    """
    out = []
    number = 1
    for line in lines:
        if line.startswith('## '):
            out.append(line[3:] + ':')
            continue
        out.append(f'{number}. {line}')
        number += 1
    return '\n\n'.join(out)


def parse_jsonld(soup):
    """Recipe fields from any schema.org Recipe in the page, or None."""
    for script in soup.find_all('script', {'type': re.compile(r'ld\+json', re.I)}):
        raw = script.string or script.get_text() or ''
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            # Some sites emit trailing commas or concatenated objects. One
            # bad block should not stop us looking at the others.
            continue

        node = find_recipe_node(data)
        if not node:
            continue

        ingredients = [clean_text(i) for i in
                       as_list(node.get('recipeIngredient') or node.get('ingredients'))]
        ingredients = [i for i in ingredients if i]

        steps = _instruction_lines(node.get('recipeInstructions'))

        tags = []
        for key in ('recipeCategory', 'recipeCuisine'):
            for tag in as_list(node.get(key)):
                tag = clean_text(tag)
                if tag and tag.lower() not in [t.lower() for t in tags]:
                    tags.append(tag)

        return {
            'name': clean_text(node.get('name')),
            'description': clean_text(node.get('description')),
            'ingredients': ingredients,
            'instructions': _number_steps(steps),
            'prep_time': parse_duration(node.get('prepTime')),
            'cook_time': parse_duration(node.get('cookTime')),
            'servings': first_int(node.get('recipeYield')),
            'image_url': first_url(node.get('image')),
            'tags': tags,
            'source': 'json-ld',
        }
    return None


# ============================================================================
# MICRODATA AND GUESSWORK
# ============================================================================

def parse_microdata(soup):
    """
    The older `itemprop` markup, for pages that still carry it.

    This is roughly what the original importer did, kept because a handful of
    older blogs and printed-recipe pages have microdata and no JSON-LD.
    """
    ingredients = [clean_text(el.get_text()) for el in
                   soup.find_all(attrs={'itemprop': re.compile(
                       r'^recipeIngredient$|^ingredients$', re.I)})]
    ingredients = [i for i in ingredients if i]

    steps = [clean_text(el.get_text()) for el in
             soup.find_all(attrs={'itemprop': re.compile(r'^recipeInstructions$', re.I)})]
    steps = [s for s in steps if s]
    if len(steps) == 1:
        # A single itemprop block holding the whole method; split on newlines
        # so it still numbers sensibly.
        steps = [line.strip() for line in steps[0].split('\n') if line.strip()]

    if not ingredients and not steps:
        return None

    def prop(name):
        el = soup.find(attrs={'itemprop': re.compile(f'^{name}$', re.I)})
        if not el:
            return None
        return el.get('datetime') or el.get('content') or el.get_text()

    name_el = soup.find(attrs={'itemprop': re.compile(r'^name$', re.I)})
    return {
        'name': clean_text(name_el.get_text()) if name_el else '',
        'description': clean_text(prop('description')),
        'ingredients': ingredients,
        'instructions': _number_steps(steps),
        'prep_time': parse_duration(prop('prepTime')),
        'cook_time': parse_duration(prop('cookTime')),
        'servings': first_int(prop('recipeYield')),
        'image_url': first_url(prop('image')),
        'tags': [],
        'source': 'microdata',
    }


def parse_guesswork(soup):
    """
    Last resort: list items whose class mentions "ingredient".

    Rarely works on a modern site, but costs nothing to try and occasionally
    rescues a self-hosted blog with no structured data at all.
    """
    ingredients = [clean_text(el.get_text()) for el in
                   soup.find_all(['li', 'span', 'p'],
                                 class_=re.compile(r'ingredient', re.I))]
    ingredients = [i for i in ingredients if i]

    steps = [clean_text(el.get_text()) for el in
             soup.find_all(['li', 'div', 'p'],
                           class_=re.compile(r'instruction|direction|step|method', re.I))]
    steps = [s for s in steps if s]

    if not ingredients:
        return None

    heading = soup.find('h1')
    return {
        'name': clean_text(heading.get_text()) if heading else '',
        'description': '',
        'ingredients': ingredients,
        'instructions': _number_steps(steps),
        'prep_time': None,
        'cook_time': None,
        'servings': None,
        'image_url': '',
        'tags': [],
        'source': 'guesswork',
    }


# ============================================================================
# PAGE TITLE AND IMAGE FALLBACKS
# ============================================================================

def _page_name(soup):
    og = soup.find('meta', {'property': 'og:title'})
    if og and og.get('content'):
        return clean_text(og['content'])
    heading = soup.find('h1')
    if heading:
        return clean_text(heading.get_text())
    if soup.title:
        return clean_text(soup.title.get_text())
    return ''


def _page_image(soup):
    for attrs in ({'property': 'og:image'}, {'name': 'twitter:image'}):
        tag = soup.find('meta', attrs)
        if tag and tag.get('content'):
            return tag['content'].strip()
    return ''


def _page_description(soup):
    for attrs in ({'name': 'description'}, {'property': 'og:description'}):
        tag = soup.find('meta', attrs)
        if tag and tag.get('content'):
            return clean_text(tag['content'])
    return ''


def parse_recipe_html(page_html, url=''):
    """
    Best recipe fields obtainable from a page, trying each strategy in turn.

    Raises ImportFailed when no strategy found any ingredients, because a
    recipe with no ingredients is not worth saving and the caller should say
    so rather than create an empty one.
    """
    soup = BeautifulSoup(page_html, 'html.parser')

    recipe = None
    for strategy in (parse_jsonld, parse_microdata, parse_guesswork):
        found = strategy(soup)
        if found and found.get('ingredients'):
            recipe = found
            break

    if recipe is None:
        raise ImportFailed(
            'No recipe data found on that page. Copy the ingredients and '
            'steps and use "paste recipe" instead.')

    # Structured data often omits the title or picture that the page itself
    # advertises, so top up anything still blank from the usual meta tags.
    if not recipe['name']:
        recipe['name'] = _page_name(soup)
    if not recipe['image_url']:
        recipe['image_url'] = _page_image(soup)
    if not recipe['description']:
        recipe['description'] = _page_description(soup)

    recipe['source_url'] = url
    return recipe


# ============================================================================
# FETCHING
# ============================================================================

def fetch_html(url, session=None, timeout=FETCH_TIMEOUT):
    """
    Fetch a page as browser-like as a plain HTTP client can manage.

    `session` is injectable so tests never touch the network.
    """
    import requests

    getter = session or requests
    try:
        response = getter.get(url, headers=BROWSER_HEADERS, timeout=timeout,
                              allow_redirects=True)
    except Exception as exc:  # requests raises a family of these
        raise ImportFailed(f'Could not reach that page: {exc}')

    status = getattr(response, 'status_code', 0)
    if status in BLOCKED_STATUSES:
        host = re.sub(r'^www\.', '', (url.split('/') + [''])[2] if '//' in url else url)
        raise ImportBlocked(
            f'{host} blocks automated requests, so the recipe cannot be '
            f'fetched here. Copy the ingredients and steps from the page and '
            f'use "paste recipe" instead.')
    if status >= 400:
        raise ImportFailed(f'That page returned HTTP {status}.')

    return response.text


def import_from_url(url, session=None):
    """Fetch and parse in one step - what the API endpoint calls."""
    return parse_recipe_html(fetch_html(url, session=session), url)


# ============================================================================
# PASTED TEXT
# ============================================================================

_INGREDIENT_HEADING = re.compile(r'^\s*#*\s*ingredients?\b[\s:]*$', re.I)
_INSTRUCTION_HEADING = re.compile(
    r'^\s*#*\s*(instructions?|directions?|method|steps?|preparation)\b[\s:]*$', re.I)
_STEP_NUMBER_RE = re.compile(r'^\s*(?:step\s*)?\d+[.)]\s*', re.I)
_NOISE_HEADING = re.compile(
    r'^\s*#*\s*(notes?|nutrition|equipment|tips?|variations?)\b[\s:]*$', re.I)


def _looks_like_ingredient(line):
    """
    An ingredient line usually starts with an amount and stays short.

    Uses the same quantity parser the pantry maths uses, so "1 1/2 cups" and
    "¾ tsp" count just as they do everywhere else in the app.
    """
    import ingredients as ing

    if len(line) > 120:
        return False
    qty, rest = ing.parse_quantity(line)
    if qty is not None and rest.strip():
        return True
    # Unit-less staples still read as ingredients when they are short and
    # have no sentence punctuation: "Salt and pepper", "Olive oil".
    return len(line) <= 40 and not re.search(r'[.!?]\s', line)


def parse_recipe_text(text, name='', url=''):
    """
    Split a pasted recipe into ingredients and steps.

    This is the way through for the sites that refuse to be fetched at all.
    Explicit "Ingredients" / "Instructions" headings are honoured when the
    paste has them, because that is by far the most reliable signal; without
    them each line is judged on whether it reads like an amount.
    """
    lines = [clean_text(line) for line in (text or '').splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        raise ImportFailed('Nothing to import - paste the recipe text first.')

    ingredients, steps = [], []
    section = None
    for line in lines:
        if _INGREDIENT_HEADING.match(line):
            section = 'ingredients'
            continue
        if _INSTRUCTION_HEADING.match(line):
            section = 'steps'
            continue
        if _NOISE_HEADING.match(line):
            section = 'skip'
            continue

        if section == 'ingredients':
            ingredients.append(line)
        elif section == 'steps':
            steps.append(_STEP_NUMBER_RE.sub('', line))
        elif section == 'skip':
            continue
        elif _looks_like_ingredient(line):
            ingredients.append(line)
        else:
            steps.append(_STEP_NUMBER_RE.sub('', line))

    # With no headings, a leading title line gets judged as a short
    # ingredient. If the caller gave no name, promote it instead - but only
    # when it carries no amount, or a paste that opens with "2 cups flour"
    # loses its first ingredient to the title.
    if not name and ingredients and section is None:
        import ingredients as ing

        if ing.parse_quantity(ingredients[0])[0] is None:
            name = ingredients.pop(0)

    if not ingredients:
        raise ImportFailed('No ingredients found in that text.')

    return {
        'name': name,
        'description': '',
        'ingredients': ingredients,
        'instructions': _number_steps(steps),
        'prep_time': None,
        'cook_time': None,
        'servings': None,
        'image_url': '',
        'tags': [],
        'source': 'pasted',
        'source_url': url,
    }
