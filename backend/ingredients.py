#!/usr/bin/env python3
"""
Ingredient parsing and unit maths for the meals <-> grocery <-> pantry loop.

Recipes store ingredients as free text ("1.5 lb chicken breast"). To generate a
grocery list that knows what is already in the pantry, and to deduct from the
pantry when a meal is cooked, that text has to become a number, a unit and a
name that can be matched across all three lists.

Nothing here touches the database; it is pure text/number work so it can be
unit-tested on its own.
"""

import re
from fractions import Fraction

# ============================================================================
# UNITS
# ============================================================================
# Each unit maps to (canonical name, dimension, factor-to-base).
# Base units: 'ml' for volume, 'g' for mass, 1 item for count.
#
# Volume and mass convert freely inside their dimension. Count units do not:
# 2 cans is not 2 heads, so container-style units only combine with themselves.
# 'each' is the generic count unit and absorbs anything unitless.

# Exact legal definitions, not rounded ones. With rounded factors a quart is
# not exactly four cups, and "2 cups + 1 quart" formats as "1.5 quart" instead
# of "1 1/2 quart" because the ratio misses a clean fraction by ~1e-6.
_FLOZ_ML = 29.5735295625          # 1 US fluid ounce, exactly

_VOLUME = {
    'tsp': _FLOZ_ML / 6, 'teaspoon': _FLOZ_ML / 6,
    'tbsp': _FLOZ_ML / 2, 'tablespoon': _FLOZ_ML / 2,
    'floz': _FLOZ_ML, 'fluidounce': _FLOZ_ML,
    'cup': _FLOZ_ML * 8,
    'pint': _FLOZ_ML * 16, 'quart': _FLOZ_ML * 32, 'gallon': _FLOZ_ML * 128,
    'ml': 1.0, 'milliliter': 1.0, 'cc': 1.0,
    'l': 1000.0, 'liter': 1000.0, 'litre': 1000.0,
}

_MASS = {
    'g': 1.0, 'gram': 1.0,
    'kg': 1000.0, 'kilogram': 1000.0,
    'oz': 28.349523125, 'ounce': 28.349523125,          # exactly 1/16 lb
    'lb': 28.349523125 * 16, 'pound': 28.349523125 * 16,
    'mg': 0.001, 'milligram': 0.001,
}

# Count-style units. Value is how many of the base item one unit represents;
# only 'dozen' is worth converting (to 'each').
_COUNT = {
    'each': 1.0, 'dozen': 12.0,
    'can': 1.0, 'jar': 1.0, 'package': 1.0, 'box': 1.0, 'bag': 1.0, 'bottle': 1.0,
    'bunch': 1.0, 'clove': 1.0, 'head': 1.0, 'stalk': 1.0, 'sprig': 1.0,
    'slice': 1.0, 'loaf': 1.0, 'stick': 1.0, 'ear': 1.0, 'fillet': 1.0,
    'pinch': 1.0, 'dash': 1.0, 'handful': 1.0,
}

# Spelling variants -> canonical unit name. Plurals are handled separately.
_UNIT_ALIASES = {
    't': 'tsp', 'ts': 'tsp', 'tspn': 'tsp',
    'tb': 'tbsp', 'tbs': 'tbsp', 'tblsp': 'tbsp', 'T': 'tbsp',
    'c': 'cup',
    'pt': 'pint', 'qt': 'quart', 'gal': 'gallon',
    'lbs': 'lb', 'pounds': 'lb',
    'ozs': 'oz',
    'pkg': 'package', 'pkgs': 'package', 'pack': 'package',
    'btl': 'bottle',
    'loaves': 'loaf',
    'ct': 'each', 'count': 'each', 'piece': 'each', 'pieces': 'each',
    'whole': 'each', 'items': 'each', 'item': 'each',
    # Spelled-out forms collapse onto the short canonical so the UI shows
    # "2 oz", never "2 ounce".
    'teaspoon': 'tsp', 'tablespoon': 'tbsp',
    'ounce': 'oz', 'fluidounce': 'floz', 'pound': 'lb',
    'gram': 'g', 'kilogram': 'kg', 'milligram': 'mg',
    'milliliter': 'ml', 'liter': 'l', 'litre': 'l', 'cc': 'ml',
}


def _unit_table(unit):
    if unit in _VOLUME:
        return _VOLUME, 'volume'
    if unit in _MASS:
        return _MASS, 'mass'
    if unit in _COUNT:
        return _COUNT, 'count'
    return None, None


def canonical_unit(raw):
    """Normalize a unit token. Returns '' when it isn't a unit we know."""
    if not raw:
        return ''
    u = str(raw).strip().lower().replace('.', '').replace('-', '').replace(' ', '')
    if not u:
        return ''
    # 'T' means tablespoon but 't' means teaspoon, so check case before lowering.
    if str(raw).strip() == 'T':
        return 'tbsp'
    u = _UNIT_ALIASES.get(u, u)
    if _unit_table(u)[0]:
        return u
    # Try de-pluralizing: cups -> cup, ounces -> ounce, pinches -> pinch
    for suffix, repl in (('ies', 'y'), ('es', ''), ('s', '')):
        if u.endswith(suffix):
            candidate = _UNIT_ALIASES.get(u[: -len(suffix)] + repl, u[: -len(suffix)] + repl)
            if _unit_table(candidate)[0]:
                return candidate
    return ''


def unit_dimension(unit):
    return _unit_table(canonical_unit(unit))[1]


def compatible(unit_a, unit_b):
    """True when two units can be added together."""
    a, b = canonical_unit(unit_a), canonical_unit(unit_b)
    da, db = _unit_table(a)[1], _unit_table(b)[1]
    if a == b:
        return True
    if da != db or da is None:
        return False
    if da == 'count':
        # Container units only merge with themselves or the generic 'each'.
        return 'each' in (a, b) or {a, b} == {'each', 'dozen'}
    return True


def to_base(qty, unit):
    """Convert a quantity to its dimension's base unit."""
    u = canonical_unit(unit)
    table, _ = _unit_table(u)
    if not table:
        return qty
    return qty * table[u]


def from_base(qty, unit):
    u = canonical_unit(unit)
    table, _ = _unit_table(u)
    if not table:
        return qty
    return qty / table[u]


def convert(qty, from_unit, to_unit):
    """Convert between two compatible units. Returns None if incompatible."""
    if not compatible(from_unit, to_unit):
        return None
    return from_base(to_base(qty, from_unit), to_unit)


# ============================================================================
# QUANTITY TEXT
# ============================================================================

_VULGAR = {
    '¼': 0.25, '½': 0.5, '¾': 0.75, '⅓': 1 / 3, '⅔': 2 / 3,
    '⅛': 0.125, '⅜': 0.375, '⅝': 0.625, '⅞': 0.875,
    '⅕': 0.2, '⅖': 0.4, '⅗': 0.6, '⅘': 0.8, '⅙': 1 / 6, '⅚': 5 / 6,
}

# "1 1/2", "1/2", "1.5", "2", "1½", "½"
_QTY_RE = re.compile(
    r'^\s*(?P<qty>'
    r'\d+\s+\d+\s*/\s*\d+'          # 1 1/2
    r'|\d+\s*/\s*\d+'                # 1/2
    r'|\d*\.\d+'                     # .5 / 1.5
    r'|\d+'                          # 2
    r')\s*(?P<vulgar>[¼½¾⅓⅔⅛⅜⅝⅞⅕⅖⅗⅘⅙⅚])?'
)
_VULGAR_ONLY_RE = re.compile(r'^\s*(?P<vulgar>[¼½¾⅓⅔⅛⅜⅝⅞⅕⅖⅗⅘⅙⅚])')
_RANGE_SEP_RE = re.compile(r'^\s*(?:-|–|—|to\b|or\b)\s*', re.I)


def _number(text):
    text = text.strip()
    if '/' in text:
        parts = text.split()
        if len(parts) == 2:                      # mixed number "1 1/2"
            whole, frac = parts
            return float(whole) + float(Fraction(frac.replace(' ', '')))
        return float(Fraction(text.replace(' ', '')))
    return float(text)


def parse_quantity(text):
    """
    Pull a leading quantity off the text.

    Returns (qty_or_None, remaining_text). Ranges ("2-3 apples") resolve to the
    upper bound so a shopping list never sends you home short.
    """
    if not text:
        return None, ''
    s = str(text).strip()

    m = _QTY_RE.match(s)
    if m:
        qty = _number(m.group('qty'))
        if m.group('vulgar'):
            qty += _VULGAR[m.group('vulgar')]
        rest = s[m.end():]
    else:
        m = _VULGAR_ONLY_RE.match(s)
        if not m:
            return None, s
        qty = _VULGAR[m.group('vulgar')]
        rest = s[m.end():]

    # Range: keep the larger end.
    sep = _RANGE_SEP_RE.match(rest)
    if sep:
        tail = rest[sep.end():]
        m2 = _QTY_RE.match(tail)
        if m2:
            second = _number(m2.group('qty'))
            if m2.group('vulgar'):
                second += _VULGAR[m2.group('vulgar')]
            qty = max(qty, second)
            rest = tail[m2.end():]

    return qty, rest.strip()


# A quantity is snapped to a whole number or a common fraction when it is
# this close. Cooking amounts are never meaningfully precise beyond 1/8, so a
# loose tolerance only ever helps: it absorbs the rounding that unit
# conversion leaves behind.
_FRACTION_TOLERANCE = 1e-4


def format_quantity(qty):
    """Render a float the way a person would write it on a list."""
    if qty is None:
        return ''
    if abs(qty - round(qty)) < _FRACTION_TOLERANCE:
        return str(int(round(qty)))
    # Prefer a tidy fraction for the common cooking amounts.
    for denom in (2, 3, 4, 8):
        scaled = qty * denom
        if abs(scaled - round(scaled)) < _FRACTION_TOLERANCE:
            whole, num = divmod(int(round(scaled)), denom)
            frac = f'{num}/{denom}'
            return f'{whole} {frac}' if whole else frac
    return f'{qty:.2f}'.rstrip('0').rstrip('.')


# Units written as words take a plural; abbreviations don't ("2 tbsp", not
# "2 tbsps"). Anything not listed is left alone.
_PLURALS = {
    'cup': 'cups', 'pint': 'pints', 'quart': 'quarts', 'gallon': 'gallons',
    'can': 'cans', 'jar': 'jars', 'bottle': 'bottles', 'package': 'packages',
    'box': 'boxes', 'bag': 'bags', 'bunch': 'bunches', 'clove': 'cloves',
    'head': 'heads', 'stalk': 'stalks', 'sprig': 'sprigs', 'slice': 'slices',
    'loaf': 'loaves', 'stick': 'sticks', 'ear': 'ears', 'fillet': 'fillets',
    'pinch': 'pinches', 'dash': 'dashes', 'handful': 'handfuls',
    'teaspoon': 'teaspoons', 'tablespoon': 'tablespoons',
}


def plural_unit(unit, qty):
    """'cup' -> 'cups' for anything but exactly one."""
    u = canonical_unit(unit)
    if qty is None or abs(qty - 1) < _FRACTION_TOLERANCE:
        return u
    return _PLURALS.get(u, u)


def format_amount(qty, unit):
    """'1 1/2 cups' / '3' / '' — what goes in the quantity column."""
    q = format_quantity(qty)
    u = canonical_unit(unit)
    if u == 'each':
        u = ''
    if q and u:
        return f'{q} {plural_unit(u, qty)}'
    return q or (u or '')


# ============================================================================
# NAME NORMALIZATION
# ============================================================================

# Stripped when they appear as standalone words. Deliberately conservative:
# 'ground' stays (ground beef), 'green'/'red' stay (green vs red pepper).
_NOISE_WORDS = {
    'fresh', 'freshly', 'organic', 'raw', 'whole', 'large', 'small', 'medium',
    'extra', 'jumbo', 'ripe', 'plain', 'pure', 'quality', 'good', 'unsalted',
    'salted', 'packed', 'divided', 'optional', 'plus', 'more', 'about',
    'approximately', 'heaping', 'scant', 'level', 'room', 'temperature',
    'cold', 'warm', 'hot', 'thinly', 'roughly', 'finely', 'coarsely', 'lightly',
}

# Prep states: dropped so "onion, diced" and "diced onion" match "onion".
_PREP_WORDS = {
    'chopped', 'diced', 'minced', 'sliced', 'shredded', 'grated',
    'peeled', 'seeded', 'stemmed', 'trimmed', 'halved', 'quartered', 'cubed',
    'julienned', 'zested', 'juiced', 'melted', 'softened', 'beaten', 'whisked',
    'drained', 'rinsed', 'washed', 'crumbled',
    'torn', 'cut', 'pitted', 'deveined', 'butterflied', 'mashed',
}

_LEADING_ARTICLES = {'a', 'an', 'the', 'of'}

_PAREN_RE = re.compile(r'\([^)]*\)')
_TRAILING_PREP_RE = re.compile(
    r',\s*(?:' + '|'.join(sorted(_PREP_WORDS | {'optional', 'divided', 'to taste'},
                                 key=len, reverse=True)) + r')\b.*$', re.I)
_TO_TASTE_RE = re.compile(r'\b(to taste|as needed|for serving|for garnish|if desired)\b', re.I)
_NON_WORD_RE = re.compile(r'[^a-z0-9\s%-]')


def _singularize(word):
    if len(word) <= 3:
        return word
    if word.endswith('ies') and len(word) > 4:
        return word[:-3] + 'y'
    if word.endswith(('ches', 'shes', 'sses', 'xes', 'zes')):
        return word[:-2]
    if word.endswith('oes'):
        return word[:-2]
    if word.endswith('s') and not word.endswith(('ss', 'us', 'is')):
        return word[:-1]
    return word


def clean_name(text):
    """Tidy an ingredient name for display: no parentheticals, no prep clause."""
    s = _PAREN_RE.sub(' ', str(text or ''))
    s = _TRAILING_PREP_RE.sub('', s)
    s = _TO_TASTE_RE.sub(' ', s)
    s = re.sub(r'\s{2,}', ' ', s).strip().strip(',').strip()
    return s


def normalize_name(text):
    """
    Reduce an ingredient name to a stable key for matching across lists.

    'Fresh Bell Peppers, diced' and '3 bell pepper' both key to 'bell pepper'.
    """
    if not text:
        return ''
    s = str(text).lower()
    s = _PAREN_RE.sub(' ', s)
    s = _TO_TASTE_RE.sub(' ', s)
    s = s.split(',')[0]              # drop trailing prep clause
    s = _NON_WORD_RE.sub(' ', s)

    words = []
    for word in s.split():
        if word in _NOISE_WORDS or word in _PREP_WORDS:
            continue
        words.append(word)
    while words and words[0] in _LEADING_ARTICLES:
        words.pop(0)
    while words and words[-1] in _LEADING_ARTICLES:
        words.pop()

    words = [_singularize(w) for w in words]
    return ' '.join(words).strip()


# ============================================================================
# CATEGORIES
# ============================================================================
# Matches config.env GROCERY_CATEGORIES: produce,dairy,meat,bakery,pantry,frozen,other

_CATEGORY_KEYWORDS = [
    ('produce', (
        'lettuce', 'spinach', 'kale', 'arugula', 'cabbage', 'carrot', 'celery',
        'onion', 'shallot', 'scallion', 'garlic', 'potato', 'tomato', 'pepper',
        'cucumber', 'zucchini', 'squash', 'broccoli', 'cauliflower', 'mushroom',
        'apple', 'banana', 'orange', 'lemon', 'lime', 'berry', 'berries',
        'strawberry', 'blueberry', 'raspberry', 'grape', 'melon', 'peach',
        'pear', 'plum', 'mango', 'avocado', 'pineapple', 'cilantro', 'parsley',
        'basil', 'thyme', 'rosemary', 'mint', 'ginger', 'corn', 'pea', 'bean sprout',
        'asparagus', 'eggplant', 'radish', 'beet', 'leek', 'herb', 'salad',
    )),
    ('dairy', (
        'milk', 'cream', 'butter', 'cheese', 'cheddar', 'mozzarella', 'parmesan',
        'feta', 'ricotta', 'yogurt', 'yoghurt', 'sour cream', 'half and half',
        'buttermilk', 'egg', 'cottage', 'creme fraiche', 'mascarpone',
    )),
    ('meat', (
        'chicken', 'beef', 'pork', 'turkey', 'lamb', 'veal', 'bacon', 'sausage',
        'ham', 'steak', 'ground', 'mince', 'salmon', 'tuna', 'shrimp', 'fish',
        'cod', 'tilapia', 'crab', 'lobster', 'scallop', 'prosciutto', 'pepperoni',
        'chorizo', 'brisket', 'ribs', 'thigh', 'breast', 'drumstick', 'roast',
    )),
    ('bakery', (
        'bread', 'roll', 'bun', 'bagel', 'tortilla', 'pita', 'baguette',
        'croissant', 'muffin', 'naan', 'brioche', 'crust', 'dough',
    )),
    ('frozen', (
        'frozen', 'ice cream', 'popsicle', 'sorbet', 'waffle',
    )),
    ('pantry', (
        'flour', 'sugar', 'salt', 'pepper corn', 'baking powder', 'baking soda',
        'yeast', 'oil', 'olive oil', 'vinegar', 'rice', 'pasta', 'noodle',
        'spaghetti', 'penne', 'ziti', 'macaroni', 'quinoa', 'oat', 'cereal',
        'bean', 'lentil', 'chickpea', 'broth', 'stock', 'sauce', 'marinara',
        'salsa', 'ketchup', 'mustard', 'mayonnaise', 'soy sauce', 'honey',
        'syrup', 'vanilla', 'cinnamon', 'cumin', 'paprika', 'oregano', 'chili',
        'spice', 'seasoning', 'can', 'canned', 'tomato paste', 'coconut milk',
        'peanut butter', 'jam', 'jelly', 'cocoa', 'chocolate', 'nut', 'almond',
        'walnut', 'pecan', 'seed', 'raisin', 'cornstarch', 'breadcrumb', 'stuffing',
    )),
]


# Checked before the keyword sweep, where a generic keyword would mislead.
_CATEGORY_OVERRIDES = (
    ('salt', 'pantry'), ('black pepper', 'pantry'), ('peppercorn', 'pantry'),
    ('red pepper flake', 'pantry'), ('chili powder', 'pantry'),
    ('pepper flake', 'pantry'), ('cayenne', 'pantry'), ('paprika', 'pantry'),
    ('crushed tomato', 'pantry'), ('tomato paste', 'pantry'),
    ('tomato sauce', 'pantry'), ('sun-dried tomato', 'pantry'),
    ('garlic powder', 'pantry'), ('onion powder', 'pantry'),
    ('coconut milk', 'pantry'), ('almond milk', 'pantry'), ('oat milk', 'pantry'),
    ('peanut butter', 'pantry'), ('apple cider vinegar', 'pantry'),
    ('lemon juice', 'pantry'), ('lime juice', 'pantry'),
    ('chicken broth', 'pantry'), ('chicken stock', 'pantry'),
    ('beef broth', 'pantry'), ('beef stock', 'pantry'),
    ('bread crumb', 'pantry'), ('breadcrumb', 'pantry'),
    ('ice cream', 'frozen'),
)


def guess_category(name):
    """Best-effort aisle for an ingredient. Falls back to 'other'."""
    key = normalize_name(name)
    if not key:
        return 'other'
    for phrase, category in _CATEGORY_OVERRIDES:
        if phrase in key:
            return category
    padded = f' {key} '
    # 'frozen peas' should beat 'pea' -> produce, so frozen is checked first.
    for category in ('frozen', 'dairy', 'meat', 'bakery', 'produce', 'pantry'):
        for cat, words in _CATEGORY_KEYWORDS:
            if cat != category:
                continue
            for word in words:
                if f' {word} ' in padded or padded.strip().endswith(f' {word}') \
                        or padded.strip() == word or padded.strip().startswith(f'{word} '):
                    return cat
    return 'other'


# ============================================================================
# PARSED INGREDIENT
# ============================================================================

class Ingredient:
    """A recipe line broken into the parts the inventory maths needs."""

    __slots__ = ('qty', 'unit', 'name', 'raw', 'optional')

    def __init__(self, qty=None, unit='', name='', raw='', optional=False):
        self.qty = qty
        self.unit = unit
        self.name = name
        self.raw = raw
        self.optional = optional

    @property
    def key(self):
        return normalize_name(self.name)

    @property
    def category(self):
        return guess_category(self.name)

    def display(self):
        amount = format_amount(self.qty, self.unit)
        return f'{amount} {self.name}'.strip() if amount else self.name

    def as_dict(self):
        return {
            'qty': self.qty, 'unit': self.unit, 'name': self.name,
            'key': self.key, 'raw': self.raw, 'optional': self.optional,
            'category': self.category, 'display': self.display(),
        }

    def __repr__(self):
        return f'Ingredient({self.qty!r}, {self.unit!r}, {self.name!r})'

    def __eq__(self, other):
        return (isinstance(other, Ingredient) and self.qty == other.qty
                and self.unit == other.unit and self.name == other.name)


def parse(text):
    """
    Parse one recipe ingredient line.

    '1.5 lb chicken breast'      -> 1.5 lb   chicken breast
    '2 (14 oz) cans tomatoes'    -> 2 can    tomatoes
    'Salt and pepper to taste'   -> None     Salt and pepper
    """
    raw = str(text or '').strip()
    if not raw:
        return Ingredient(raw=raw)

    optional = bool(re.search(r'\b(optional)\b', raw, re.I))
    working = re.sub(r'^\s*(?:a|an)\s+(?=[a-z])', '1 ', raw, flags=re.I)

    qty, rest = parse_quantity(working)

    # A parenthetical right after the number is pack size ("2 (14 oz) cans"),
    # which we don't need once we know the container count.
    rest = re.sub(r'^\s*\([^)]*\)\s*', ' ', rest).strip()

    # The next token may be a unit.
    unit = ''
    parts = rest.split(None, 1)
    if parts:
        candidate = canonical_unit(parts[0])
        if candidate:
            # "1 cup sugar" -> unit cup. But "3 bananas" must not read 'bananas'
            # as a unit, and a bare unit with nothing after it is the name.
            if len(parts) > 1:
                unit = candidate
                rest = parts[1].strip()
            elif qty is None:
                unit = ''
    # "of" after a unit: "1 cup of sugar"
    rest = re.sub(r'^of\s+', '', rest, flags=re.I).strip()

    if qty is not None and not unit:
        unit = 'each'

    name = clean_name(rest) or clean_name(raw) or raw
    return Ingredient(qty=qty, unit=unit, name=name, raw=raw, optional=optional)


def parse_all(lines):
    return [parse(line) for line in (lines or []) if str(line or '').strip()]


# ============================================================================
# INVENTORY MATHS
# ============================================================================

def add_amounts(qty_a, unit_a, qty_b, unit_b):
    """
    Add two amounts, answering in the first one's unit.

    Returns (qty, unit). If the units don't combine, the first amount is
    returned unchanged and the caller should keep the second as its own line.
    """
    if qty_a is None:
        return (qty_b, unit_b) if qty_b is not None else (None, unit_a or unit_b)
    if qty_b is None:
        return qty_a, unit_a
    if not compatible(unit_a, unit_b):
        return None, unit_a          # unknown total: treat as unquantified
    converted = convert(qty_b, unit_b, unit_a)
    if converted is None:
        return None, unit_a
    return qty_a + converted, unit_a


def subtract_amounts(needed_qty, needed_unit, have_qty, have_unit):
    """
    Take what's on hand off what a recipe needs.

    Returns (remaining_qty, unit, covered) where covered is True when the
    pantry fully satisfies the requirement. An unquantified requirement
    ('salt to taste') counts as covered if the pantry has the item at all.
    """
    if needed_qty is None:
        return None, needed_unit, have_qty is not None or bool(have_unit)
    if have_qty is None:
        return needed_qty, needed_unit, False
    if not compatible(needed_unit, have_unit):
        # Can't compare cups to pounds — assume it doesn't cover the need.
        return needed_qty, needed_unit, False
    have_converted = convert(have_qty, have_unit, needed_unit)
    if have_converted is None:
        return needed_qty, needed_unit, False
    remaining = needed_qty - have_converted
    if remaining <= 1e-9:
        return 0.0, needed_unit, True
    return remaining, needed_unit, False


def aggregate(ingredients):
    """
    Combine parsed ingredients that refer to the same thing.

    Returns a list of dicts: {key, name, qty, unit, category, sources[], raw[]}.
    Amounts that can't be combined (cups of one, pounds of another) collapse to
    an unquantified entry rather than inventing a number.
    """
    buckets = {}
    order = []
    for ing in ingredients:
        key = ing.key
        if not key:
            continue
        if key not in buckets:
            buckets[key] = {
                'key': key, 'name': ing.name, 'qty': ing.qty, 'unit': ing.unit,
                'category': ing.category, 'sources': [], 'raw': [ing.raw],
                'optional': ing.optional,
            }
            order.append(key)
        else:
            bucket = buckets[key]
            bucket['qty'], bucket['unit'] = add_amounts(
                bucket['qty'], bucket['unit'], ing.qty, ing.unit)
            bucket['raw'].append(ing.raw)
            bucket['optional'] = bucket['optional'] and ing.optional
            # Prefer the shorter, cleaner name for display.
            if len(ing.name) < len(bucket['name']):
                bucket['name'] = ing.name
    return [buckets[k] for k in order]
