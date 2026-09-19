#!/usr/bin/env python3
"""
Family Dashboard Backend API
Handles recipes, meals, grocery lists, pantry, calendar, weather, and settings
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import logging
import os
import requests
from bs4 import BeautifulSoup
import json
import re
import uuid
from urllib.parse import urlparse

from calendar_sync import (CalendarSync, DEFAULT_COLORS, read_raw_config,
                           write_raw_config, test_calendar)
import ingredients as ing

# Paths
basedir = os.path.abspath(os.path.dirname(__file__))
project_root = os.path.abspath(os.path.join(basedir, '..'))
config_dir = os.path.join(project_root, 'config')

# Load config.env (project root) into the environment. Values already set in
# the real environment win, so systemd overrides still work.
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(project_root, 'config.env'), override=False)
except ImportError:
    pass

logging.basicConfig(
    level=getattr(logging, os.environ.get('LOG_LEVEL', 'INFO').upper(), logging.INFO),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
log = logging.getLogger('dashboard')

app = Flask(__name__, static_folder=os.path.join(project_root, 'frontend'), static_url_path='')
CORS(app)

# Configuration
# DASHBOARD_DB overrides the database location (used by the test suite; also
# handy for putting the db on external storage).
_db_path = os.environ.get('DASHBOARD_DB') or os.path.join(basedir, 'dashboard.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{_db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'family-dashboard-secret-key-change-in-production')

LOCATION_NAME = os.environ.get('LOCATION_NAME', 'Rochester, NY').strip('"')
LOCATION_LAT = float(os.environ.get('LOCATION_LAT', 43.1566))
LOCATION_LON = float(os.environ.get('LOCATION_LON', -77.6088))
EXPIRATION_WARNING_DAYS = int(os.environ.get('EXPIRATION_WARNING_DAYS', 7))

db = SQLAlchemy(app)

# Calendar sync service (background thread started in main / init_db)
_calendars_file = os.environ.get('CALENDARS_FILE') or os.path.join(config_dir, 'calendars.json')
calendar_sync = CalendarSync(
    config_path=os.path.join(project_root, _calendars_file),  # no-op if already absolute
    refresh_interval=int(os.environ.get('CALENDAR_REFRESH_INTERVAL', 300)),
    lookahead_days=int(os.environ.get('CALENDAR_LOOKAHEAD_DAYS', 14)),
)

# ============================================================================
# DATABASE MODELS
# ============================================================================

class Recipe(db.Model):
    """Recipe storage with ingredients and instructions"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    source_url = db.Column(db.String(500))
    prep_time = db.Column(db.Integer)  # minutes
    cook_time = db.Column(db.Integer)  # minutes
    servings = db.Column(db.Integer)
    ingredients = db.Column(db.Text)  # JSON array
    instructions = db.Column(db.Text)
    tags = db.Column(db.String(500))  # comma-separated
    image_url = db.Column(db.String(500))
    favorite = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class MealPlan(db.Model):
    """Weekly meal planning"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.String(20))  # breakfast, lunch, dinner, snack
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'))
    recipe = db.relationship('Recipe', backref='meal_plans')
    custom_meal = db.Column(db.String(200))  # for non-recipe meals
    notes = db.Column(db.Text)
    servings = db.Column(db.Integer)         # overrides the recipe's own yield
    cooked_at = db.Column(db.DateTime)       # set when the meal deducted from the pantry
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GroceryItem(db.Model):
    """Grocery shopping list"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.String(50))          # display text, e.g. "1 1/2 cup"
    qty = db.Column(db.Float)                    # parsed amount, None = unquantified
    unit = db.Column(db.String(20))              # canonical unit for qty
    match_key = db.Column(db.String(200), index=True)  # normalized name, links the lists
    category = db.Column(db.String(50))  # produce, dairy, meat, etc.
    checked = db.Column(db.Boolean, default=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'))
    recipe = db.relationship('Recipe')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    list_id = db.Column(db.Integer, default=1)  # support multiple lists

class PantryItem(db.Model):
    """Pantry inventory tracking"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.String(50))          # display text, e.g. "2 lb"
    qty = db.Column(db.Float)                    # parsed amount
    unit = db.Column(db.String(20))              # canonical unit
    match_key = db.Column(db.String(200), index=True)  # links to recipes/grocery
    category = db.Column(db.String(50))
    expiration_date = db.Column(db.Date)
    location = db.Column(db.String(100))  # pantry, fridge, freezer
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Photo(db.Model):
    """An image uploaded from the app for the kiosk slideshow."""
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)   # stored name under photos/
    original_name = db.Column(db.String(255))
    caption = db.Column(db.String(200))
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    bytes = db.Column(db.Integer)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Settings(db.Model):
    """System settings"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ============================================================================
# INVENTORY HELPERS
# ============================================================================
# Recipes, the grocery list and the pantry are all the same thing seen from
# three angles: an amount of a named item. `match_key` (ingredients.normalize_name)
# is what lets a row in one list find its counterpart in another.

GROCERY_CATEGORIES = [c.strip() for c in os.environ.get(
    'GROCERY_CATEGORIES', 'produce,dairy,meat,bakery,pantry,frozen,other').split(',') if c.strip()]
PANTRY_LOCATIONS = [c.strip() for c in os.environ.get(
    'PANTRY_LOCATIONS', 'pantry,fridge,freezer').split(',') if c.strip()]


def _amount_from_text(text, name=''):
    """
    Read a stored quantity string ("2 lb", "6 cans", "1 gal") into (qty, unit).

    Falls back to parsing the whole 'name' when the quantity column is empty,
    so hand-typed rows like "2 lb ground beef" still get a number.
    """
    qty, rest = ing.parse_quantity(text or '')
    unit = ''
    if rest:
        unit = ing.canonical_unit(rest.split()[0])
    if qty is None and not unit and name:
        parsed = ing.parse(name)
        return parsed.qty, parsed.unit
    if qty is not None and not unit:
        unit = 'each'
    return qty, unit


def _set_amount(item, qty, unit):
    """Write a numeric amount onto a grocery/pantry row, keeping display text in sync."""
    item.qty = qty
    item.unit = ing.canonical_unit(unit) or (unit or '')
    item.quantity = ing.format_amount(qty, item.unit)
    return item


def _sync_row(item, name=None, quantity=None, category=None):
    """
    Normalize a grocery/pantry row after a create or edit.

    Accepts whatever the client sent (a name that may embed its own amount, a
    free-text quantity) and derives match_key, qty, unit and category from it.
    """
    if name is not None:
        item.name = name
    parsed = ing.parse(item.name or '')
    # A name like "2 lb ground beef" carries its own amount; lift it out so the
    # list shows "ground beef" with quantity "2 lb".
    if parsed.qty is not None and not (quantity or '').strip():
        item.name = parsed.name or item.name
        _set_amount(item, parsed.qty, parsed.unit)
    elif quantity is not None:
        qty, unit = _amount_from_text(quantity, item.name)
        if qty is None and (quantity or '').strip():
            # Unparseable but meaningful ("a few", "2 boxes-ish") - keep the text.
            item.qty, item.unit, item.quantity = None, '', quantity.strip()
        else:
            _set_amount(item, qty, unit)
    item.match_key = ing.normalize_name(item.name)
    if category:
        item.category = category
    elif not item.category or item.category in ('generated', '', 'other'):
        item.category = ing.guess_category(item.name)
    return item


def _serialize_grocery(item, pantry_index=None):
    data = {
        'id': item.id,
        'name': item.name,
        'quantity': item.quantity or '',
        'qty': item.qty,
        'unit': item.unit or '',
        'category': item.category,
        'checked': bool(item.checked),
        'recipe_id': item.recipe_id,
        'recipe_name': item.recipe.name if item.recipe else None,
        'match_key': item.match_key,
    }
    if pantry_index is not None:
        stock = pantry_index.get(item.match_key)
        data['in_pantry'] = bool(stock)
        data['pantry_amount'] = _stock_display(stock)
    return data


def _serialize_pantry(item):
    return {
        'id': item.id,
        'name': item.name,
        'quantity': item.quantity or '',
        'qty': item.qty,
        'unit': item.unit or '',
        'category': item.category,
        'expiration_date': item.expiration_date.isoformat() if item.expiration_date else None,
        'location': item.location,
        'notes': item.notes,
        'match_key': item.match_key,
    }


def _pantry_index(items=None):
    """
    Stock per match_key: {key: {'amounts': [(qty, unit), ...], 'items': [PantryItem]}}.

    Amounts are kept as a list rather than one total because a pantry can
    legitimately hold the same item in units that don't add up - an unopened
    16 oz bottle of olive oil and 4 tbsp left in another. Collapsing those to a
    single number would either invent a figure or throw the stock away, and the
    second is what made a well-stocked item read as missing. Callers ask for a
    total in the unit they care about via _stock_in_unit().
    """
    index = {}
    for item in (items if items is not None else PantryItem.query.all()):
        key = item.match_key or ing.normalize_name(item.name)
        if not key:
            continue
        entry = index.setdefault(key, {'amounts': [], 'items': []})
        entry['amounts'].append((item.qty, item.unit or ''))
        entry['items'].append(item)
    return index


def _stock_in_unit(entry, unit):
    """
    How much of this item the pantry holds, expressed in `unit`.

    Returns None when no row can be converted into that unit (incompatible
    dimensions, or stock recorded without a number).
    """
    if not entry:
        return None
    total = None
    for qty, row_unit in entry['amounts']:
        if qty is None:
            continue
        converted = ing.convert(qty, row_unit or 'each', unit or 'each')
        if converted is None:
            continue
        total = converted if total is None else total + converted
    return total


def _stock_display(entry):
    """Readable total for the UI: '2 lb', or '16 oz + 4 tbsp' when units differ."""
    if not entry:
        return ''
    groups = []                         # [(qty, unit)] one per compatible family
    unquantified = False
    for qty, unit in entry['amounts']:
        if qty is None:
            unquantified = True
            continue
        for i, (gq, gu) in enumerate(groups):
            if ing.compatible(gu, unit or 'each'):
                converted = ing.convert(qty, unit or 'each', gu)
                if converted is not None:
                    groups[i] = (gq + converted, gu)
                    break
        else:
            groups.append((qty, ing.canonical_unit(unit) or 'each'))
    parts = [ing.format_amount(q, u) for q, u in groups]
    if not parts and unquantified:
        return 'in stock'
    return ' + '.join(p for p in parts if p)


def _covers(entry, needed_qty, needed_unit):
    """Does pantry stock satisfy this requirement? -> (remaining, unit, covered)."""
    if not entry:
        return needed_qty, needed_unit, False
    if needed_qty is None:
        # Unquantified need ('salt to taste') is covered if we have the item.
        return None, needed_unit, True
    have = _stock_in_unit(entry, needed_unit)
    return ing.subtract_amounts(needed_qty, needed_unit, have, needed_unit)


def _deduct_from_pantry(entry, qty, unit):
    """
    Consume an amount from the pantry rows behind one match_key.

    Rows are drained oldest-expiring first; a row that hits zero is deleted.
    Returns (consumed_display, shortfall_qty, shortfall_unit).
    """
    rows = sorted(entry['items'], key=lambda i: (i.expiration_date is None, i.expiration_date))
    if qty is None:
        # Unquantified need ("salt to taste") - take nothing, it's a staple.
        return '', None, ''

    remaining = qty
    consumed = 0.0
    for row in rows:
        if remaining <= 1e-9:
            break
        if row.qty is None:
            continue
        available = ing.convert(row.qty, row.unit or 'each', unit)
        if available is None:
            continue                       # incompatible unit, leave this row alone
        take = min(available, remaining)
        remaining -= take
        consumed += take
        left = available - take
        if left <= 1e-9:
            db.session.delete(row)
        else:
            _set_amount(row, ing.convert(left, unit, row.unit or 'each'), row.unit or 'each')
    shortfall = remaining if remaining > 1e-9 else None
    return ing.format_amount(consumed, unit) if consumed else '', shortfall, unit


def _add_to_pantry(key, name, qty, unit, category=None, location='pantry', expiration_date=None):
    """
    Put an amount into the pantry, merging into an existing row when the units
    agree. Returns (PantryItem, created).
    """
    key = key or ing.normalize_name(name)
    existing = (PantryItem.query.filter_by(match_key=key, location=location).first()
                or PantryItem.query.filter_by(match_key=key).first())
    if existing and (qty is None or existing.qty is None or ing.compatible(existing.unit or 'each', unit or 'each')):
        total, total_unit = ing.add_amounts(existing.qty, existing.unit or '', qty, unit or '')
        _set_amount(existing, total, total_unit)
        if expiration_date:
            existing.expiration_date = expiration_date
        existing.updated_at = datetime.utcnow()
        return existing, False

    item = PantryItem(
        name=name,
        category=category or ing.guess_category(name),
        location=location,
        expiration_date=expiration_date,
        notes='',
    )
    _set_amount(item, qty, unit)
    item.match_key = key
    db.session.add(item)
    return item, True


def _meal_ingredients(meal):
    """Parsed ingredients for one planned meal, scaled if servings were overridden."""
    if not meal.recipe or not meal.recipe.ingredients:
        return []
    try:
        lines = json.loads(meal.recipe.ingredients)
    except (ValueError, TypeError):
        return []
    parsed = ing.parse_all(lines)
    base = meal.recipe.servings or 0
    want = meal.servings or 0
    if base and want and base != want:
        factor = want / float(base)
        for item in parsed:
            if item.qty is not None:
                item.qty *= factor
    return parsed

# ============================================================================
# RECIPE ENDPOINTS
# ============================================================================

@app.route('/api/recipes', methods=['GET', 'POST'])
def recipes():
    if request.method == 'GET':
        search = request.args.get('search', '')
        tag = request.args.get('tag', '')
        favorite = request.args.get('favorite', '')
        
        query = Recipe.query
        
        if search:
            query = query.filter(Recipe.name.contains(search) | Recipe.description.contains(search))
        if tag:
            query = query.filter(Recipe.tags.contains(tag))
        if favorite:
            query = query.filter_by(favorite=True)
            
        recipes = query.order_by(Recipe.name).all()
        
        return jsonify([{
            'id': r.id,
            'name': r.name,
            'description': r.description,
            'source_url': r.source_url,
            'prep_time': r.prep_time,
            'cook_time': r.cook_time,
            'servings': r.servings,
            'ingredients': json.loads(r.ingredients) if r.ingredients else [],
            'instructions': r.instructions,
            'tags': r.tags.split(',') if r.tags else [],
            'image_url': r.image_url,
            'favorite': r.favorite,
            'created_at': r.created_at.isoformat(),
        } for r in recipes])
    
    elif request.method == 'POST':
        data = request.json
        
        recipe = Recipe(
            name=data['name'],
            description=data.get('description', ''),
            source_url=data.get('source_url', ''),
            prep_time=data.get('prep_time'),
            cook_time=data.get('cook_time'),
            servings=data.get('servings'),
            ingredients=json.dumps(data.get('ingredients', [])),
            instructions=data.get('instructions', ''),
            tags=','.join(data.get('tags', [])),
            image_url=data.get('image_url', ''),
            favorite=data.get('favorite', False)
        )
        
        db.session.add(recipe)
        db.session.commit()
        
        return jsonify({'id': recipe.id, 'message': 'Recipe created'}), 201

@app.route('/api/recipes/<int:recipe_id>', methods=['GET', 'PUT', 'DELETE'])
def recipe_detail(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    
    if request.method == 'GET':
        return jsonify({
            'id': recipe.id,
            'name': recipe.name,
            'description': recipe.description,
            'source_url': recipe.source_url,
            'prep_time': recipe.prep_time,
            'cook_time': recipe.cook_time,
            'servings': recipe.servings,
            'ingredients': json.loads(recipe.ingredients) if recipe.ingredients else [],
            'instructions': recipe.instructions,
            'tags': recipe.tags.split(',') if recipe.tags else [],
            'image_url': recipe.image_url,
            'favorite': recipe.favorite,
        })
    
    elif request.method == 'PUT':
        data = request.json
        
        recipe.name = data.get('name', recipe.name)
        recipe.description = data.get('description', recipe.description)
        recipe.source_url = data.get('source_url', recipe.source_url)
        recipe.prep_time = data.get('prep_time', recipe.prep_time)
        recipe.cook_time = data.get('cook_time', recipe.cook_time)
        recipe.servings = data.get('servings', recipe.servings)
        recipe.ingredients = json.dumps(data.get('ingredients', json.loads(recipe.ingredients or '[]')))
        recipe.instructions = data.get('instructions', recipe.instructions)
        recipe.tags = ','.join(data.get('tags', recipe.tags.split(',') if recipe.tags else []))
        recipe.image_url = data.get('image_url', recipe.image_url)
        recipe.favorite = data.get('favorite', recipe.favorite)
        
        db.session.commit()
        
        return jsonify({'message': 'Recipe updated'})
    
    elif request.method == 'DELETE':
        db.session.delete(recipe)
        db.session.commit()
        
        return jsonify({'message': 'Recipe deleted'})

@app.route('/api/recipes/import-url', methods=['POST'])
def import_recipe_url():
    """Import recipe from URL using web scraping"""
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL required'}), 400
    
    try:
        # Fetch the page
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try to extract recipe data
        recipe_data = {
            'name': '',
            'description': '',
            'source_url': url,
            'ingredients': [],
            'instructions': '',
            'prep_time': None,
            'cook_time': None,
            'servings': None,
            'image_url': ''
        }
        
        # Extract title
        title_elem = soup.find('h1') or soup.find('title')
        if title_elem:
            recipe_data['name'] = title_elem.get_text().strip()
        
        # Extract meta description
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc:
            recipe_data['description'] = meta_desc.get('content', '').strip()
        
        # Extract image
        og_image = soup.find('meta', {'property': 'og:image'})
        if og_image:
            recipe_data['image_url'] = og_image.get('content', '')
        
        # Try to find ingredients (common patterns)
        ingredient_patterns = [
            soup.find_all('li', class_=re.compile('ingredient', re.I)),
            soup.find_all('li', {'itemprop': 'recipeIngredient'}),
            soup.find_all('span', {'itemprop': 'recipeIngredient'})
        ]
        
        for pattern in ingredient_patterns:
            if pattern:
                recipe_data['ingredients'] = [ing.get_text().strip() for ing in pattern]
                break
        
        # Try to find instructions
        instruction_patterns = [
            soup.find_all('li', class_=re.compile('instruction', re.I)),
            soup.find_all('li', {'itemprop': 'recipeInstructions'}),
            soup.find('div', {'itemprop': 'recipeInstructions'})
        ]
        
        for pattern in instruction_patterns:
            if pattern:
                if isinstance(pattern, list):
                    recipe_data['instructions'] = '\n\n'.join([
                        f"{i+1}. {inst.get_text().strip()}" 
                        for i, inst in enumerate(pattern)
                    ])
                else:
                    recipe_data['instructions'] = pattern.get_text().strip()
                break
        
        # Try to extract times
        prep_time = soup.find('time', {'itemprop': 'prepTime'})
        if prep_time:
            # Parse ISO duration format (PT15M)
            duration = prep_time.get('datetime', '')
            minutes = re.search(r'PT(\d+)M', duration)
            if minutes:
                recipe_data['prep_time'] = int(minutes.group(1))
        
        cook_time = soup.find('time', {'itemprop': 'cookTime'})
        if cook_time:
            duration = cook_time.get('datetime', '')
            minutes = re.search(r'PT(\d+)M', duration)
            if minutes:
                recipe_data['cook_time'] = int(minutes.group(1))
        
        # Extract servings
        servings = soup.find('span', {'itemprop': 'recipeYield'})
        if servings:
            yield_text = servings.get_text().strip()
            numbers = re.search(r'\d+', yield_text)
            if numbers:
                recipe_data['servings'] = int(numbers.group(0))
        
        return jsonify(recipe_data)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# MEAL PLAN ENDPOINTS
# ============================================================================

@app.route('/api/meals', methods=['GET', 'POST'])
def meals():
    if request.method == 'GET':
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        query = MealPlan.query
        
        if start_date:
            query = query.filter(MealPlan.date >= datetime.fromisoformat(start_date).date())
        if end_date:
            query = query.filter(MealPlan.date <= datetime.fromisoformat(end_date).date())
        
        meals = query.order_by(MealPlan.date, MealPlan.meal_type).all()

        # Ingredient coverage per meal, so the planner can show "4/6 on hand"
        # without a round-trip per row.
        index = _pantry_index() if request.args.get('with_availability') else None

        def coverage(m):
            if index is None:
                return {}
            items = _meal_ingredients(m)
            if not items:
                return {'total': 0, 'have': 0}
            have = 0
            for item in items:
                _, _, covered = _covers(index.get(item.key), item.qty, item.unit)
                have += 1 if covered else 0
            return {'total': len(items), 'have': have}

        return jsonify([{
            'id': m.id,
            'date': m.date.isoformat(),
            'meal_type': m.meal_type,
            'recipe_id': m.recipe_id,
            'recipe_name': m.recipe.name if m.recipe else m.custom_meal,
            'custom_meal': m.custom_meal,
            'notes': m.notes,
            'servings': m.servings,
            'cooked_at': m.cooked_at.isoformat() if m.cooked_at else None,
            **coverage(m),
        } for m in meals])
    
    elif request.method == 'POST':
        data = request.json
        
        meal = MealPlan(
            date=datetime.fromisoformat(data['date']).date(),
            meal_type=data['meal_type'],
            recipe_id=data.get('recipe_id'),
            custom_meal=data.get('custom_meal'),
            notes=data.get('notes', ''),
            servings=data.get('servings'),
        )
        
        db.session.add(meal)
        db.session.commit()
        
        return jsonify({'id': meal.id, 'message': 'Meal planned'}), 201

@app.route('/api/meals/<int:meal_id>', methods=['PUT', 'DELETE'])
def meal_detail(meal_id):
    meal = MealPlan.query.get_or_404(meal_id)
    
    if request.method == 'PUT':
        data = request.json
        
        meal.date = datetime.fromisoformat(data.get('date', meal.date.isoformat())).date()
        meal.meal_type = data.get('meal_type', meal.meal_type)
        meal.recipe_id = data.get('recipe_id', meal.recipe_id)
        meal.custom_meal = data.get('custom_meal', meal.custom_meal)
        meal.notes = data.get('notes', meal.notes)
        meal.servings = data.get('servings', meal.servings)
        
        db.session.commit()
        
        return jsonify({'message': 'Meal updated'})
    
    elif request.method == 'DELETE':
        db.session.delete(meal)
        db.session.commit()
        
        return jsonify({'message': 'Meal deleted'})

@app.route('/api/meals/<int:meal_id>/availability', methods=['GET'])
def meal_availability(meal_id):
    """
    What this meal needs versus what the pantry holds.

    Powers the "4 of 6 ingredients on hand" badge and tells you what to buy
    before cooking.
    """
    meal = MealPlan.query.get_or_404(meal_id)
    pantry = _pantry_index()

    lines = []
    have = 0
    for item in _meal_ingredients(meal):
        stock = pantry.get(item.key)
        remaining, unit, covered = _covers(stock, item.qty, item.unit)
        if covered:
            have += 1
        lines.append({
            'name': item.name,
            'needed': ing.format_amount(item.qty, item.unit),
            'in_pantry': _stock_display(stock),
            'have': covered,
            'short': ing.format_amount(remaining, unit) if not covered and remaining else '',
            'optional': item.optional,
            'key': item.key,
        })

    return jsonify({
        'meal_id': meal.id,
        'recipe_name': meal.recipe.name if meal.recipe else meal.custom_meal,
        'cooked_at': meal.cooked_at.isoformat() if meal.cooked_at else None,
        'total': len(lines),
        'have': have,
        'missing': [l for l in lines if not l['have']],
        'ingredients': lines,
    })


@app.route('/api/meals/<int:meal_id>/cook', methods=['POST'])
def cook_meal(meal_id):
    """
    Mark a meal cooked and take its ingredients out of the pantry.

    Deducts oldest-expiring stock first. Anything the pantry was short of is
    reported back (and optionally added to the grocery list) rather than
    silently going negative.
    """
    meal = MealPlan.query.get_or_404(meal_id)
    data = request.json or {}
    add_shortfall = data.get('add_missing_to_grocery', False)

    if meal.cooked_at and not data.get('force'):
        return jsonify({'error': 'This meal is already marked cooked',
                        'cooked_at': meal.cooked_at.isoformat()}), 409
    if not meal.recipe:
        return jsonify({'error': 'This meal has no recipe to deduct from'}), 400

    pantry = _pantry_index()
    consumed, short = [], []

    for item in _meal_ingredients(meal):
        entry = pantry.get(item.key)
        if not entry:
            if item.qty is not None:
                short.append({'name': item.name,
                              'needed': ing.format_amount(item.qty, item.unit)})
            continue
        used, shortfall, unit = _deduct_from_pantry(entry, item.qty, item.unit)
        if used:
            consumed.append({'name': item.name, 'used': used})
        if shortfall:
            short.append({'name': item.name, 'needed': ing.format_amount(shortfall, unit)})

    if add_shortfall:
        for missing in short:
            key = ing.normalize_name(missing['name'])
            if GroceryItem.query.filter_by(match_key=key, checked=False).first():
                continue
            row = GroceryItem(name=missing['name'], match_key=key,
                              category=ing.guess_category(missing['name']))
            qty, unit = _amount_from_text(missing['needed'], missing['name'])
            _set_amount(row, qty, unit)
            db.session.add(row)

    meal.cooked_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'message': f"{meal.recipe.name} cooked — {len(consumed)} item(s) used from the pantry"
                   + (f", {len(short)} short" if short else ''),
        'consumed': consumed,
        'short': short,
        'added_to_grocery': add_shortfall,
        'cooked_at': meal.cooked_at.isoformat(),
    })


@app.route('/api/meals/<int:meal_id>/uncook', methods=['POST'])
def uncook_meal(meal_id):
    """Undo the cooked flag (does not put ingredients back)."""
    meal = MealPlan.query.get_or_404(meal_id)
    meal.cooked_at = None
    db.session.commit()
    return jsonify({'message': 'Meal marked not cooked'})


# ============================================================================
# GROCERY LIST ENDPOINTS
# ============================================================================

@app.route('/api/grocery', methods=['GET', 'POST'])
def grocery_list():
    if request.method == 'GET':
        list_id = request.args.get('list_id', 1, type=int)
        items = GroceryItem.query.filter_by(list_id=list_id).order_by(GroceryItem.category, GroceryItem.name).all()
        # Flag anything the pantry already covers so you don't buy it twice.
        index = _pantry_index()
        return jsonify([_serialize_grocery(item, index) for item in items])

    elif request.method == 'POST':
        data = request.json or {}
        item = GroceryItem(
            name=data['name'],
            recipe_id=data.get('recipe_id'),
            list_id=data.get('list_id', 1),
        )
        _sync_row(item, name=data['name'], quantity=data.get('quantity', ''),
                  category=data.get('category'))
        db.session.add(item)
        db.session.commit()
        return jsonify(_serialize_grocery(item)), 201


@app.route('/api/grocery/<int:item_id>', methods=['PUT', 'DELETE'])
def grocery_item(item_id):
    item = GroceryItem.query.get_or_404(item_id)

    if request.method == 'PUT':
        data = request.json or {}
        if 'checked' in data:
            item.checked = bool(data['checked'])
        if any(k in data for k in ('name', 'quantity', 'category')):
            _sync_row(item,
                      name=data.get('name', item.name),
                      quantity=data.get('quantity', item.quantity),
                      category=data.get('category'))
        db.session.commit()
        return jsonify(_serialize_grocery(item))

    elif request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'message': 'Item deleted'})


@app.route('/api/grocery/generate', methods=['POST'])
def generate_grocery_list():
    """
    Build the shopping list from the meal plan, minus what's already in the pantry.

    Ingredients from every planned recipe in the range are parsed, combined
    (1 cup milk + 1/2 cup milk = 1 1/2 cup milk), checked against pantry stock,
    and merged into the existing list rather than duplicated.
    """
    data = request.json or {}
    start_date = datetime.fromisoformat(data['start_date']).date()
    end_date = datetime.fromisoformat(data['end_date']).date()
    use_pantry = data.get('use_pantry', True)
    include_optional = data.get('include_optional', True)
    list_id = data.get('list_id', 1)

    meals = MealPlan.query.filter(
        MealPlan.date >= start_date,
        MealPlan.date <= end_date,
        MealPlan.recipe_id.isnot(None)
    ).all()

    # Collect every ingredient, remembering which recipe asked for it.
    parsed = []
    recipe_for_key = {}
    for meal in meals:
        for item in _meal_ingredients(meal):
            if item.optional and not include_optional:
                continue
            parsed.append(item)
            recipe_for_key.setdefault(item.key, meal.recipe_id)

    needed = ing.aggregate(parsed)
    pantry = _pantry_index() if use_pantry else {}

    existing_rows = {}
    for row in GroceryItem.query.filter_by(list_id=list_id, checked=False).all():
        existing_rows.setdefault(row.match_key or ing.normalize_name(row.name), row)

    added, merged, skipped = [], [], []

    for entry in needed:
        key = entry['key']
        qty, unit = entry['qty'], entry['unit']

        # 1. Take off what the pantry already has.
        if key in pantry:
            stock = pantry[key]
            qty, unit, covered = _covers(stock, qty, unit)
            if covered:
                skipped.append({
                    'name': entry['name'],
                    'reason': 'in pantry',
                    'pantry_amount': _stock_display(stock),
                })
                continue

        # 2. Merge into a row already on the list instead of adding a duplicate.
        row = existing_rows.get(key)
        if row is not None:
            before = ing.format_amount(row.qty, row.unit or '')
            total, total_unit = ing.add_amounts(row.qty, row.unit or '', qty, unit)
            _set_amount(row, total, total_unit)
            if row.recipe_id is None:
                row.recipe_id = recipe_for_key.get(key)
            merged.append({'name': row.name, 'from': before,
                           'to': ing.format_amount(row.qty, row.unit or '')})
            continue

        # 3. New row.
        item = GroceryItem(
            name=entry['name'],
            category=entry['category'],
            recipe_id=recipe_for_key.get(key),
            list_id=list_id,
            match_key=key,
        )
        _set_amount(item, qty, unit)
        db.session.add(item)
        existing_rows[key] = item
        added.append({'name': item.name, 'quantity': item.quantity, 'category': item.category})

    db.session.commit()

    parts = []
    if added:
        parts.append(f"{len(added)} item{'s' if len(added) != 1 else ''} added")
    if merged:
        parts.append(f"{len(merged)} updated")
    if skipped:
        parts.append(f"{len(skipped)} already in the pantry")
    message = ', '.join(parts) if parts else 'Nothing to add — the list already covers these meals'

    return jsonify({
        'message': message,
        'meals': len(meals),
        'added': added,
        'merged': merged,
        'skipped': skipped,
    })


@app.route('/api/grocery/clear-checked', methods=['POST'])
def clear_checked_grocery():
    """
    Clear bought items off the list and stock them into the pantry.

    This is the restock half of the loop: what you ticked off in the aisle
    becomes inventory. Pass {"to_pantry": false} to just delete them.
    """
    data = request.json or {}
    to_pantry = data.get('to_pantry', True)
    location = data.get('location', 'pantry')
    list_id = data.get('list_id', 1)

    items = GroceryItem.query.filter_by(checked=True, list_id=list_id).all()
    stocked = []

    if to_pantry:
        for item in items:
            key = item.match_key or ing.normalize_name(item.name)
            if not key:
                continue
            pantry_item, created = _add_to_pantry(
                key=key, name=item.name, qty=item.qty, unit=item.unit or '',
                category=item.category, location=location)
            stocked.append({
                'name': pantry_item.name,
                'quantity': pantry_item.quantity,
                'created': created,
            })

    count = len(items)
    for item in items:
        db.session.delete(item)
    db.session.commit()

    if not count:
        message = 'Nothing checked off'
    elif to_pantry:
        message = f"{count} item{'s' if count != 1 else ''} moved to the pantry"
    else:
        message = f"{count} item{'s' if count != 1 else ''} cleared"

    return jsonify({'message': message, 'cleared': count, 'stocked': stocked})


# ============================================================================
# PANTRY ENDPOINTS
# ============================================================================

@app.route('/api/pantry', methods=['GET', 'POST'])
def pantry():
    if request.method == 'GET':
        location = request.args.get('location')
        expiring_soon = request.args.get('expiring_soon')

        query = PantryItem.query
        if location:
            query = query.filter_by(location=location)
        if expiring_soon:
            days = request.args.get('days', EXPIRATION_WARNING_DAYS, type=int)
            cutoff = datetime.now().date() + timedelta(days=days)
            query = query.filter(
                PantryItem.expiration_date.isnot(None),
                PantryItem.expiration_date <= cutoff
            )

        items = query.order_by(PantryItem.location, PantryItem.name).all()
        return jsonify([_serialize_pantry(item) for item in items])

    elif request.method == 'POST':
        data = request.json or {}
        exp_date = None
        if data.get('expiration_date'):
            exp_date = datetime.fromisoformat(data['expiration_date']).date()

        item = PantryItem(
            name=data['name'],
            location=data.get('location', 'pantry'),
            expiration_date=exp_date,
            notes=data.get('notes', ''),
        )
        _sync_row(item, name=data['name'], quantity=data.get('quantity', ''),
                  category=data.get('category'))
        db.session.add(item)
        db.session.commit()
        return jsonify(_serialize_pantry(item)), 201


@app.route('/api/pantry/<int:item_id>', methods=['PUT', 'DELETE'])
def pantry_item(item_id):
    item = PantryItem.query.get_or_404(item_id)

    if request.method == 'PUT':
        data = request.json or {}
        item.location = data.get('location', item.location)
        item.notes = data.get('notes', item.notes)
        if 'expiration_date' in data:
            item.expiration_date = (datetime.fromisoformat(data['expiration_date']).date()
                                    if data['expiration_date'] else None)
        if any(k in data for k in ('name', 'quantity', 'category')):
            _sync_row(item,
                      name=data.get('name', item.name),
                      quantity=data.get('quantity', item.quantity),
                      category=data.get('category'))
        db.session.commit()
        return jsonify(_serialize_pantry(item))

    elif request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        return jsonify({'message': 'Item deleted'})


@app.route('/api/pantry/<int:item_id>/to-grocery', methods=['POST'])
def pantry_to_grocery(item_id):
    """Running low on something? Put it straight on the shopping list."""
    item = PantryItem.query.get_or_404(item_id)
    data = request.json or {}
    list_id = data.get('list_id', 1)
    key = item.match_key or ing.normalize_name(item.name)

    existing = GroceryItem.query.filter_by(match_key=key, checked=False, list_id=list_id).first()
    if existing:
        return jsonify({'message': f'{item.name} is already on the list',
                        'item': _serialize_grocery(existing), 'created': False})

    row = GroceryItem(name=item.name, category=item.category, list_id=list_id, match_key=key)
    qty, unit = _amount_from_text(data.get('quantity', ''), item.name)
    _set_amount(row, qty, unit)
    db.session.add(row)
    db.session.commit()
    return jsonify({'message': f'{item.name} added to the grocery list',
                    'item': _serialize_grocery(row), 'created': True}), 201


# ============================================================================
# CALENDAR & WEATHER ENDPOINTS
# ============================================================================

@app.route('/api/calendar/events', methods=['GET'])
def calendar_events():
    """
    Events from every configured calendar (config/calendars.json) that overlap
    [start_date, end_date). Defaults to today. Dates are ISO 8601; a bare
    YYYY-MM-DD is treated as local midnight.
    """
    events = calendar_sync.get_events(
        request.args.get('start_date'),
        request.args.get('end_date'),
    )
    return jsonify(events)

@app.route('/api/calendar/status', methods=['GET'])
def calendar_status():
    """Which calendars are configured and whether the last sync succeeded."""
    return jsonify(calendar_sync.status())

@app.route('/api/calendar/refresh', methods=['POST'])
def calendar_refresh():
    """Force an immediate re-sync of all calendars."""
    calendar_sync.refresh()
    return jsonify(calendar_sync.status())

# ---- Calendar management (reads/writes config/calendars.json) --------------

CALENDAR_FIELDS = ('name', 'type', 'url', 'username', 'password', 'color', 'calendars', 'enabled')

def _slugify(text):
    slug = re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')
    return slug or 'calendar'

def _unique_calendar_id(name, existing_ids):
    base = _slugify(name)
    candidate, n = base, 2
    while candidate in existing_ids:
        candidate, n = f'{base}-{n}', n + 1
    return candidate

def _public_calendar(entry, index, status_by_id):
    """Calendar entry as sent to the browser: no password, plus sync status."""
    public = {k: v for k, v in entry.items() if k != 'password'}
    public.setdefault('type', 'ics')
    public.setdefault('enabled', True)
    if not public.get('color'):
        public['color'] = DEFAULT_COLORS[index % len(DEFAULT_COLORS)]
    password = entry.get('password') or ''
    public['has_password'] = bool(password)
    # ${VAR} references aren't secrets; show them so the user knows what's wired up
    public['password_ref'] = password if password.startswith('${') else None
    public['status'] = status_by_id.get(entry.get('id'))
    return public

def _validate_calendar_payload(data, existing=None):
    """Merge a request body over an existing entry and validate. Returns (entry, error)."""
    entry = dict(existing or {})
    for key in CALENDAR_FIELDS:
        if key in data:
            entry[key] = data[key]

    entry['name'] = str(entry.get('name') or '').strip()
    entry['type'] = str(entry.get('type') or 'ics').strip().lower()
    entry['url'] = str(entry.get('url') or '').strip()
    if entry['type'] in ('ical', 'webcal'):
        entry['type'] = 'ics'
    if not entry['name']:
        return None, 'Name is required'
    if entry['type'] not in ('ics', 'caldav'):
        return None, "Type must be 'ics' or 'caldav'"
    if not entry['url']:
        return None, 'URL is required'
    if not re.match(r'^(https?|webcal)://', entry['url'], re.I):
        return None, 'URL must start with http://, https:// or webcal://'

    # Blank password in an edit means "keep the existing one"
    if not entry.get('password') and existing and existing.get('password'):
        entry['password'] = existing['password']
    for key in ('username', 'password'):
        if key in entry and not entry[key]:
            del entry[key]

    cals = entry.get('calendars')
    if isinstance(cals, str):
        cals = [c.strip() for c in cals.split(',')]
    if cals is not None:
        cals = [str(c).strip() for c in cals if str(c).strip()]
        if cals and entry['type'] == 'caldav':
            entry['calendars'] = cals
        else:
            entry.pop('calendars', None)

    color = str(entry.get('color') or '').strip()
    if color and not re.match(r'^#[0-9a-fA-F]{6}$', color):
        return None, 'Color must be a hex value like #4f8ef7'
    if color:
        entry['color'] = color
    else:
        entry.pop('color', None)

    entry['enabled'] = bool(entry.get('enabled', True))
    return entry, None

def _apply_calendar_config(entries):
    write_raw_config(calendar_sync.config_path, entries)
    calendar_sync.reload()
    calendar_sync.refresh_async()

@app.route('/api/calendar/calendars', methods=['GET'])
def list_calendars():
    """All configured calendars (passwords omitted) with their last-sync status."""
    status_by_id = {c['id']: c for c in calendar_sync.status()['calendars']}
    entries = read_raw_config(calendar_sync.config_path)
    return jsonify([_public_calendar(e, i, status_by_id) for i, e in enumerate(entries)])

@app.route('/api/calendar/calendars', methods=['POST'])
def add_calendar():
    data = request.get_json(silent=True) or {}
    entry, error = _validate_calendar_payload(data)
    if error:
        return jsonify({'error': error}), 400
    entries = read_raw_config(calendar_sync.config_path)
    entry['id'] = _unique_calendar_id(entry['name'], {e.get('id') for e in entries})
    entries.append(entry)
    _apply_calendar_config(entries)
    return jsonify(_public_calendar(entry, len(entries) - 1, {})), 201

@app.route('/api/calendar/calendars/<cal_id>', methods=['PUT', 'DELETE'])
def calendar_detail(cal_id):
    entries = read_raw_config(calendar_sync.config_path)
    index = next((i for i, e in enumerate(entries) if e.get('id') == cal_id), None)
    if index is None:
        return jsonify({'error': 'Calendar not found'}), 404

    if request.method == 'DELETE':
        entries.pop(index)
        _apply_calendar_config(entries)
        return jsonify({'message': 'Calendar deleted'})

    data = request.get_json(silent=True) or {}
    entry, error = _validate_calendar_payload(data, existing=entries[index])
    if error:
        return jsonify({'error': error}), 400
    entry['id'] = cal_id
    entries[index] = entry
    _apply_calendar_config(entries)
    return jsonify(_public_calendar(entry, index, {}))

@app.route('/api/calendar/test', methods=['POST'])
def calendar_test():
    """
    Fetch a calendar right now without saving it. Body is the same shape as
    POST /api/calendar/calendars; include "id" to reuse the stored password
    of an existing calendar when the password field is left blank.
    """
    data = dict(request.get_json(silent=True) or {})
    if not str(data.get('name') or '').strip():
        data['name'] = 'Test'  # a name isn't needed just to check connectivity
    existing = None
    if data.get('id'):
        existing = next((e for e in read_raw_config(calendar_sync.config_path)
                         if e.get('id') == data['id']), None)
    entry, error = _validate_calendar_payload(data, existing=existing)
    if error:
        return jsonify({'ok': False, 'error': error}), 400
    entry.setdefault('id', 'test')
    return jsonify(test_calendar(entry, calendar_sync.tz))

@app.route('/api/weather', methods=['GET'])
def weather():
    """Get weather for the configured location (LOCATION_LAT/LON in config.env)"""
    # Using National Weather Service API (free, no key required)
    try:
        lat, lon = LOCATION_LAT, LOCATION_LON
        
        # Get grid point
        point_url = f'https://api.weather.gov/points/{lat},{lon}'
        point_response = requests.get(point_url, timeout=10)
        point_data = point_response.json()
        
        # Get forecast
        forecast_url = point_data['properties']['forecast']
        forecast_response = requests.get(forecast_url, timeout=10)
        forecast_data = forecast_response.json()
        
        # Get alerts
        alerts_url = f'https://api.weather.gov/alerts/active?point={lat},{lon}'
        alerts_response = requests.get(alerts_url, timeout=10)
        alerts_data = alerts_response.json()
        
        periods = forecast_data['properties']['periods'][:5]  # Next 5 periods
        
        return jsonify({
            'location': LOCATION_NAME,
            'current': {
                'temperature': periods[0]['temperature'],
                'temperatureUnit': periods[0]['temperatureUnit'],
                'shortForecast': periods[0]['shortForecast'],
                'detailedForecast': periods[0]['detailedForecast'],
                'windSpeed': periods[0]['windSpeed'],
                'windDirection': periods[0]['windDirection'],
            },
            'forecast': [{
                'name': p['name'],
                'temperature': p['temperature'],
                'temperatureUnit': p['temperatureUnit'],
                'shortForecast': p['shortForecast'],
                'windSpeed': p['windSpeed'],
            } for p in periods[1:]],
            'alerts': [{
                'event': alert['properties']['event'],
                'headline': alert['properties']['headline'],
                'description': alert['properties']['description'],
                'severity': alert['properties']['severity'],
                'urgency': alert['properties']['urgency'],
            } for alert in alerts_data.get('features', [])]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# DISPLAY & PHOTO ENDPOINTS
# ============================================================================
# The kiosk reads its whole appearance from `display_config` and polls
# `revision` so edits made in the phone app appear on the wall within seconds.

PHOTO_DIR = os.environ.get('DASHBOARD_PHOTOS') or os.path.join(basedir, 'photos')
ALLOWED_PHOTO_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif'}
MAX_PHOTO_EDGE = 1920          # downscale for a Pi's GPU and disk
PHOTO_QUALITY = 85
app.config['MAX_CONTENT_LENGTH'] = 30 * 1024 * 1024   # per-request upload cap

# Screens the kiosk knows how to render. The app can hide and reorder them but
# not invent new ones.
SCREEN_TYPES = {
    'calendar': 'Calendar & Weather',
    'meals': 'Meal Plan',
    'grocery': 'Grocery List',
    'recipes': 'Recipes & Pantry',
    'photos': 'Photos',
}

DEFAULT_DISPLAY = {
    'rotation_interval': 30,
    'clock_24h': False,
    'show_indicators': True,
    'theme': {
        'primary': '#667eea',
        'secondary': '#764ba2',
        'text': '#ffffff',
        'accent': '#ffd166',
        'font': "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        'card_opacity': 0.10,
        'scale': 1.0,
    },
    'screens': [
        {'id': 'calendar', 'enabled': True, 'duration': None},
        {'id': 'meals', 'enabled': True, 'duration': None},
        {'id': 'grocery', 'enabled': True, 'duration': None},
        {'id': 'recipes', 'enabled': True, 'duration': None},
        {'id': 'photos', 'enabled': False, 'duration': 60,
         'options': {'interval': 8, 'shuffle': True, 'captions': True}},
    ],
    'screensaver': {
        'enabled': False,
        'idle_seconds': 300,
        'interval': 8,
        'shuffle': True,
        'show_clock': True,
    },
}

_HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}$')


def _clamp(value, low, high, fallback):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number:                      # NaN
        return fallback
    return max(low, min(high, number))


def _color(value, fallback):
    value = str(value or '').strip()
    return value if _HEX_RE.match(value) else fallback


def _validate_display(incoming):
    """
    Merge a client payload onto the defaults, dropping anything unsafe.

    Unknown screen ids are ignored; the order of the list is the rotation order.
    """
    incoming = incoming if isinstance(incoming, dict) else {}
    base = json.loads(json.dumps(DEFAULT_DISPLAY))   # deep copy

    base['rotation_interval'] = int(_clamp(
        incoming.get('rotation_interval', base['rotation_interval']), 5, 3600,
        base['rotation_interval']))
    base['clock_24h'] = bool(incoming.get('clock_24h', base['clock_24h']))
    base['show_indicators'] = bool(incoming.get('show_indicators', base['show_indicators']))

    theme_in = incoming.get('theme') or {}
    theme = base['theme']
    for key in ('primary', 'secondary', 'text', 'accent'):
        theme[key] = _color(theme_in.get(key), theme[key])
    font = str(theme_in.get('font') or '').strip()
    # Font stacks go straight into CSS, so keep the characters boring.
    if font and len(font) <= 200 and not re.search(r'[<>{};@\\]', font):
        theme['font'] = font
    theme['card_opacity'] = round(_clamp(theme_in.get('card_opacity'), 0.0, 0.6,
                                         theme['card_opacity']), 3)
    theme['scale'] = round(_clamp(theme_in.get('scale'), 0.6, 1.6, theme['scale']), 3)

    screens_in = incoming.get('screens')
    if isinstance(screens_in, list) and screens_in:
        defaults_by_id = {s['id']: s for s in base['screens']}
        seen, screens = set(), []
        for entry in screens_in:
            if not isinstance(entry, dict):
                continue
            sid = str(entry.get('id') or '')
            if sid not in SCREEN_TYPES or sid in seen:
                continue
            seen.add(sid)
            merged = dict(defaults_by_id[sid])
            merged['enabled'] = bool(entry.get('enabled', merged['enabled']))
            duration = entry.get('duration', merged.get('duration'))
            merged['duration'] = (None if duration in (None, '', 0)
                                  else int(_clamp(duration, 5, 3600, 30)))
            if sid == 'photos':
                opts_in = entry.get('options') or {}
                opts = dict(merged.get('options') or {})
                opts['interval'] = int(_clamp(opts_in.get('interval'), 2, 600,
                                              opts.get('interval', 8)))
                opts['shuffle'] = bool(opts_in.get('shuffle', opts.get('shuffle', True)))
                opts['captions'] = bool(opts_in.get('captions', opts.get('captions', True)))
                merged['options'] = opts
            screens.append(merged)
        # Any screen the client didn't mention keeps its default, appended last,
        # so a new screen type in a future version isn't silently lost.
        for screen in base['screens']:
            if screen['id'] not in seen:
                screens.append(screen)
        base['screens'] = screens

    saver_in = incoming.get('screensaver') or {}
    saver = base['screensaver']
    saver['enabled'] = bool(saver_in.get('enabled', saver['enabled']))
    saver['idle_seconds'] = int(_clamp(saver_in.get('idle_seconds'), 30, 86400,
                                       saver['idle_seconds']))
    saver['interval'] = int(_clamp(saver_in.get('interval'), 2, 600, saver['interval']))
    saver['shuffle'] = bool(saver_in.get('shuffle', saver['shuffle']))
    saver['show_clock'] = bool(saver_in.get('show_clock', saver['show_clock']))

    return base


def _get_setting(key, default=None):
    row = Settings.query.filter_by(key=key).first()
    return row.value if row else default


def _put_setting(key, value):
    row = Settings.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(Settings(key=key, value=value))


def _display_config():
    raw = _get_setting('display_config')
    if not raw:
        return json.loads(json.dumps(DEFAULT_DISPLAY))
    try:
        return _validate_display(json.loads(raw))
    except (ValueError, TypeError):
        log.warning('display_config is not valid JSON; falling back to defaults')
        return json.loads(json.dumps(DEFAULT_DISPLAY))


def _bump_revision():
    """Any change the kiosk should pick up bumps this counter."""
    try:
        current = int(_get_setting('display_revision', '0') or '0')
    except (TypeError, ValueError):
        current = 0
    _put_setting('display_revision', str(current + 1))
    return current + 1


def _photo_url(photo):
    return f'/photos/{photo.filename}'


def _serialize_photo(photo):
    return {
        'id': photo.id,
        'url': _photo_url(photo),
        'filename': photo.filename,
        'caption': photo.caption or '',
        'width': photo.width,
        'height': photo.height,
        'bytes': photo.bytes,
        'sort_order': photo.sort_order or 0,
        'created_at': photo.created_at.isoformat() if photo.created_at else None,
    }


@app.route('/api/display', methods=['GET', 'PUT'])
def display_config():
    if request.method == 'GET':
        photos = Photo.query.order_by(Photo.sort_order, Photo.id).all()
        return jsonify({
            'config': _display_config(),
            'revision': int(_get_setting('display_revision', '0') or '0'),
            'screen_types': SCREEN_TYPES,
            'photos': [_serialize_photo(p) for p in photos],
        })

    config = _validate_display(request.json or {})
    _put_setting('display_config', json.dumps(config))
    revision = _bump_revision()
    db.session.commit()
    return jsonify({'message': 'Display updated', 'config': config, 'revision': revision})


@app.route('/api/display/reset', methods=['POST'])
def reset_display_config():
    _put_setting('display_config', json.dumps(DEFAULT_DISPLAY))
    revision = _bump_revision()
    db.session.commit()
    return jsonify({'message': 'Display reset to defaults',
                    'config': json.loads(json.dumps(DEFAULT_DISPLAY)), 'revision': revision})


@app.route('/api/display/revision', methods=['GET'])
def display_revision():
    """Cheap poll for the kiosk: has anything changed since revision N?"""
    return jsonify({'revision': int(_get_setting('display_revision', '0') or '0')})


# ---- Photos ---------------------------------------------------------------

def _store_photo(file_storage):
    """
    Save an uploaded image, downscaling it when Pillow is available.

    Returns a Photo (not yet committed) or raises ValueError with a reason.
    """
    original = os.path.basename(file_storage.filename or 'photo')
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED_PHOTO_EXT:
        raise ValueError(f'{original}: not an image we can show '
                         f'({", ".join(sorted(ALLOWED_PHOTO_EXT))})')

    os.makedirs(PHOTO_DIR, exist_ok=True)
    stored_ext = '.jpg' if ext in ('.heic', '.heif') else ext
    filename = f'{uuid.uuid4().hex}{stored_ext}'
    path = os.path.join(PHOTO_DIR, filename)

    width = height = None
    try:
        from PIL import Image, ImageOps
        try:                                   # iPhone HEIC support, if installed
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            if ext in ('.heic', '.heif'):
                raise ValueError(
                    f'{original}: HEIC photos need pillow-heif on the Pi '
                    '(pip install pillow-heif), or share them as JPEG')

        file_storage.stream.seek(0)
        with Image.open(file_storage.stream) as img:
            img = ImageOps.exif_transpose(img)     # honour the phone's rotation
            if img.mode in ('RGBA', 'P', 'LA') and stored_ext in ('.jpg', '.jpeg'):
                img = img.convert('RGB')
            img.thumbnail((MAX_PHOTO_EDGE, MAX_PHOTO_EDGE), Image.LANCZOS)
            width, height = img.size
            save_args = {'quality': PHOTO_QUALITY, 'optimize': True} \
                if stored_ext in ('.jpg', '.jpeg') else {}
            img.save(path, **save_args)
    except ImportError:
        # No Pillow: store the original bytes untouched. Fine for a handful of
        # photos; install Pillow on the Pi for large albums.
        if ext in ('.heic', '.heif'):
            raise ValueError(f'{original}: HEIC needs Pillow installed on the Pi')
        file_storage.stream.seek(0)
        file_storage.save(path)

    photo = Photo(
        filename=filename,
        original_name=original[:255],
        caption='',
        width=width,
        height=height,
        bytes=os.path.getsize(path),
        sort_order=(db.session.query(db.func.max(Photo.sort_order)).scalar() or 0) + 1,
    )
    return photo


@app.route('/api/photos', methods=['GET', 'POST'])
def photos():
    if request.method == 'GET':
        rows = Photo.query.order_by(Photo.sort_order, Photo.id).all()
        return jsonify([_serialize_photo(p) for p in rows])

    files = request.files.getlist('files') or request.files.getlist('file')
    if not files:
        return jsonify({'error': 'No file uploaded'}), 400

    saved, errors = [], []
    for file_storage in files:
        if not file_storage or not file_storage.filename:
            continue
        try:
            photo = _store_photo(file_storage)
            db.session.add(photo)
            db.session.flush()
            saved.append(_serialize_photo(photo))
        except ValueError as err:
            errors.append(str(err))
        except Exception as err:               # noqa: BLE001 - report, don't 500
            log.exception('photo upload failed')
            errors.append(f'{file_storage.filename}: {err}')

    if saved:
        _bump_revision()
    db.session.commit()

    if not saved:
        return jsonify({'error': '; '.join(errors) or 'Nothing uploaded'}), 400
    return jsonify({'message': f"{len(saved)} photo{'s' if len(saved) != 1 else ''} added",
                    'photos': saved, 'errors': errors}), 201


@app.route('/api/photos/<int:photo_id>', methods=['PUT', 'DELETE'])
def photo_detail(photo_id):
    photo = Photo.query.get_or_404(photo_id)

    if request.method == 'PUT':
        data = request.json or {}
        if 'caption' in data:
            photo.caption = str(data['caption'] or '')[:200]
        if 'sort_order' in data:
            photo.sort_order = int(_clamp(data['sort_order'], 0, 100000, photo.sort_order or 0))
        _bump_revision()
        db.session.commit()
        return jsonify(_serialize_photo(photo))

    path = os.path.join(PHOTO_DIR, photo.filename)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError as err:
            log.warning('could not remove %s: %s', path, err)
    db.session.delete(photo)
    _bump_revision()
    db.session.commit()
    return jsonify({'message': 'Photo deleted'})


@app.route('/api/photos/reorder', methods=['POST'])
def reorder_photos():
    """Body: {"ids": [3, 1, 2]} — the new slideshow order."""
    ids = (request.json or {}).get('ids') or []
    for position, photo_id in enumerate(ids):
        photo = db.session.get(Photo, photo_id)
        if photo:
            photo.sort_order = position
    _bump_revision()
    db.session.commit()
    return jsonify({'message': 'Order saved'})


@app.route('/photos/<path:filename>')
def serve_photo(filename):
    """Serve an uploaded photo to the kiosk / app."""
    return send_from_directory(PHOTO_DIR, filename)


# ============================================================================
# SETTINGS ENDPOINTS
# ============================================================================

@app.route('/api/settings', methods=['GET'])
def get_settings():
    settings = Settings.query.all()
    return jsonify({s.key: s.value for s in settings})

@app.route('/api/settings/<key>', methods=['GET', 'PUT'])
def setting(key):
    if request.method == 'GET':
        setting = Settings.query.filter_by(key=key).first()
        return jsonify({'key': key, 'value': setting.value if setting else None})
    
    elif request.method == 'PUT':
        data = request.json
        setting = Settings.query.filter_by(key=key).first()
        
        if setting:
            setting.value = data['value']
        else:
            setting = Settings(key=key, value=data['value'])
            db.session.add(setting)
        
        db.session.commit()
        
        return jsonify({'message': 'Setting updated'})

# ============================================================================
# FRONTEND ROUTES
# ============================================================================

APP_VERSION = '1.0.0'

@app.route('/api/health', methods=['GET'])
def health():
    """Used by the iOS app / PWA to find and verify a dashboard server."""
    import socket
    return jsonify({
        'app': 'familydash',
        'version': APP_VERSION,
        'hostname': socket.gethostname(),
        'location': LOCATION_NAME,
        'calendars': len(calendar_sync.calendars),
        'time': datetime.now().astimezone().isoformat(),
    })

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/mobile')
def mobile():
    return send_from_directory(app.static_folder, 'mobile.html')

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def _migrate_schema():
    """
    Add columns introduced after a dashboard was already installed.

    SQLAlchemy's create_all() only creates missing *tables*, so a Pi that has
    been running since before the inventory features would keep its old
    grocery/pantry tables and every query would fail. SQLite can add columns
    in place, which is all we need.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    wanted = {
        'grocery_item': {
            'qty': 'FLOAT',
            'unit': 'VARCHAR(20)',
            'match_key': 'VARCHAR(200)',
        },
        'pantry_item': {
            'qty': 'FLOAT',
            'unit': 'VARCHAR(20)',
            'match_key': 'VARCHAR(200)',
        },
        'meal_plan': {
            'servings': 'INTEGER',
            'cooked_at': 'DATETIME',
        },
    }

    added = []
    existing_tables = set(inspector.get_table_names())
    for table, columns in wanted.items():
        if table not in existing_tables:
            continue                               # create_all() just made it
        present = {c['name'] for c in inspector.get_columns(table)}
        for column, ddl in columns.items():
            if column in present:
                continue
            with db.engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))
            added.append(f'{table}.{column}')

    if added:
        log.info('Schema updated: added %s', ', '.join(added))
    return added


def _backfill_match_keys():
    """
    Give existing grocery/pantry rows the parsed amounts the new features need.

    Runs once: rows that already have a match_key are left alone.
    """
    touched = 0
    for model in (GroceryItem, PantryItem):
        for row in model.query.filter((model.match_key.is_(None)) | (model.match_key == '')).all():
            _sync_row(row, quantity=row.quantity)
            touched += 1
    if touched:
        db.session.commit()
        log.info('Backfilled %d existing item(s) with parsed amounts', touched)
    return touched


def init_db():
    """Initialize database with default settings"""
    with app.app_context():
        db.create_all()
        _migrate_schema()

        # Add default settings if they don't exist
        default_settings = {
            'screen_rotation_interval': '30',  # seconds
            'motion_timeout': '300',  # seconds (5 minutes)
            'default_screen': '0',
            'location': 'Rochester, NY',
            'temperature_unit': 'F',
            'display_config': json.dumps(DEFAULT_DISPLAY),
            'display_revision': '1',
        }

        for key, value in default_settings.items():
            if not Settings.query.filter_by(key=key).first():
                db.session.add(Settings(key=key, value=value))

        db.session.commit()
        _backfill_match_keys()
        os.makedirs(PHOTO_DIR, exist_ok=True)
        log.info("Database initialized")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    init_db()

    if calendar_sync.enabled:
        log.info("Calendar sync: %d calendar(s) configured, refreshing every %ss",
                 len(calendar_sync.calendars), calendar_sync.refresh_interval)
        calendar_sync.start()
    else:
        log.warning("Calendar sync disabled - create config/calendars.json "
                    "(see calendars.example.json) to show real events")

    host = os.environ.get('API_HOST', '0.0.0.0')  # 0.0.0.0 allows access from other devices
    port = int(os.environ.get('API_PORT', 5000))
    debug = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'
    # use_reloader=False: the reloader would fork a second process and a second sync thread
    # load_dotenv=False: we already loaded config.env; don't let Flask scan parent dirs for .env
    app.run(host=host, port=port, debug=debug, use_reloader=False, load_dotenv=False)
