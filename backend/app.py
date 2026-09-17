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
from urllib.parse import urlparse

from calendar_sync import CalendarSync

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
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "dashboard.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'family-dashboard-secret-key-change-in-production')

LOCATION_NAME = os.environ.get('LOCATION_NAME', 'Rochester, NY').strip('"')
LOCATION_LAT = float(os.environ.get('LOCATION_LAT', 43.1566))
LOCATION_LON = float(os.environ.get('LOCATION_LON', -77.6088))

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class GroceryItem(db.Model):
    """Grocery shopping list"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.String(50))
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
    quantity = db.Column(db.String(50))
    category = db.Column(db.String(50))
    expiration_date = db.Column(db.Date)
    location = db.Column(db.String(100))  # pantry, fridge, freezer
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Settings(db.Model):
    """System settings"""
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
        
        return jsonify([{
            'id': m.id,
            'date': m.date.isoformat(),
            'meal_type': m.meal_type,
            'recipe_id': m.recipe_id,
            'recipe_name': m.recipe.name if m.recipe else m.custom_meal,
            'custom_meal': m.custom_meal,
            'notes': m.notes,
        } for m in meals])
    
    elif request.method == 'POST':
        data = request.json
        
        meal = MealPlan(
            date=datetime.fromisoformat(data['date']).date(),
            meal_type=data['meal_type'],
            recipe_id=data.get('recipe_id'),
            custom_meal=data.get('custom_meal'),
            notes=data.get('notes', '')
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
        
        db.session.commit()
        
        return jsonify({'message': 'Meal updated'})
    
    elif request.method == 'DELETE':
        db.session.delete(meal)
        db.session.commit()
        
        return jsonify({'message': 'Meal deleted'})

# ============================================================================
# GROCERY LIST ENDPOINTS
# ============================================================================

@app.route('/api/grocery', methods=['GET', 'POST'])
def grocery_list():
    if request.method == 'GET':
        list_id = request.args.get('list_id', 1, type=int)
        items = GroceryItem.query.filter_by(list_id=list_id).order_by(GroceryItem.category, GroceryItem.name).all()
        
        return jsonify([{
            'id': item.id,
            'name': item.name,
            'quantity': item.quantity,
            'category': item.category,
            'checked': item.checked,
            'recipe_id': item.recipe_id,
            'recipe_name': item.recipe.name if item.recipe else None,
        } for item in items])
    
    elif request.method == 'POST':
        data = request.json
        
        item = GroceryItem(
            name=data['name'],
            quantity=data.get('quantity', ''),
            category=data.get('category', 'other'),
            recipe_id=data.get('recipe_id'),
            list_id=data.get('list_id', 1)
        )
        
        db.session.add(item)
        db.session.commit()
        
        return jsonify({'id': item.id, 'message': 'Item added'}), 201

@app.route('/api/grocery/<int:item_id>', methods=['PUT', 'DELETE'])
def grocery_item(item_id):
    item = GroceryItem.query.get_or_404(item_id)
    
    if request.method == 'PUT':
        data = request.json
        
        item.name = data.get('name', item.name)
        item.quantity = data.get('quantity', item.quantity)
        item.category = data.get('category', item.category)
        item.checked = data.get('checked', item.checked)
        
        db.session.commit()
        
        return jsonify({'message': 'Item updated'})
    
    elif request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        
        return jsonify({'message': 'Item deleted'})

@app.route('/api/grocery/generate', methods=['POST'])
def generate_grocery_list():
    """Generate grocery list from meal plan"""
    data = request.json
    start_date = datetime.fromisoformat(data['start_date']).date()
    end_date = datetime.fromisoformat(data['end_date']).date()
    
    # Get all meals in date range
    meals = MealPlan.query.filter(
        MealPlan.date >= start_date,
        MealPlan.date <= end_date,
        MealPlan.recipe_id.isnot(None)
    ).all()
    
    # Aggregate ingredients
    ingredient_map = {}
    
    for meal in meals:
        if meal.recipe and meal.recipe.ingredients:
            ingredients = json.loads(meal.recipe.ingredients)
            for ing in ingredients:
                # Simple aggregation - in production, use better parsing
                name = ing.lower().strip()
                if name in ingredient_map:
                    ingredient_map[name]['count'] += 1
                else:
                    ingredient_map[name] = {'text': ing, 'count': 1}
    
    # Create grocery items
    created_count = 0
    for name, data in ingredient_map.items():
        # Check if already exists
        existing = GroceryItem.query.filter_by(name=data['text'], checked=False).first()
        if not existing:
            item = GroceryItem(
                name=data['text'],
                quantity=str(data['count']) if data['count'] > 1 else '',
                category='generated'
            )
            db.session.add(item)
            created_count += 1
    
    db.session.commit()
    
    return jsonify({'message': f'{created_count} items added to grocery list'})

@app.route('/api/grocery/clear-checked', methods=['POST'])
def clear_checked_grocery():
    """Remove all checked items"""
    GroceryItem.query.filter_by(checked=True).delete()
    db.session.commit()
    return jsonify({'message': 'Checked items cleared'})

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
            # Items expiring in next 7 days
            week_from_now = datetime.now().date() + timedelta(days=7)
            query = query.filter(
                PantryItem.expiration_date.isnot(None),
                PantryItem.expiration_date <= week_from_now
            )
        
        items = query.order_by(PantryItem.location, PantryItem.name).all()
        
        return jsonify([{
            'id': item.id,
            'name': item.name,
            'quantity': item.quantity,
            'category': item.category,
            'expiration_date': item.expiration_date.isoformat() if item.expiration_date else None,
            'location': item.location,
            'notes': item.notes,
        } for item in items])
    
    elif request.method == 'POST':
        data = request.json
        
        exp_date = None
        if data.get('expiration_date'):
            exp_date = datetime.fromisoformat(data['expiration_date']).date()
        
        item = PantryItem(
            name=data['name'],
            quantity=data.get('quantity', ''),
            category=data.get('category', 'other'),
            expiration_date=exp_date,
            location=data.get('location', 'pantry'),
            notes=data.get('notes', '')
        )
        
        db.session.add(item)
        db.session.commit()
        
        return jsonify({'id': item.id, 'message': 'Item added'}), 201

@app.route('/api/pantry/<int:item_id>', methods=['PUT', 'DELETE'])
def pantry_item(item_id):
    item = PantryItem.query.get_or_404(item_id)
    
    if request.method == 'PUT':
        data = request.json
        
        item.name = data.get('name', item.name)
        item.quantity = data.get('quantity', item.quantity)
        item.category = data.get('category', item.category)
        item.location = data.get('location', item.location)
        item.notes = data.get('notes', item.notes)
        
        if data.get('expiration_date'):
            item.expiration_date = datetime.fromisoformat(data['expiration_date']).date()
        
        db.session.commit()
        
        return jsonify({'message': 'Item updated'})
    
    elif request.method == 'DELETE':
        db.session.delete(item)
        db.session.commit()
        
        return jsonify({'message': 'Item deleted'})

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

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/mobile')
def mobile():
    return send_from_directory(app.static_folder, 'mobile.html')

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_db():
    """Initialize database with default settings"""
    with app.app_context():
        db.create_all()
        
        # Add default settings if they don't exist
        default_settings = {
            'screen_rotation_interval': '30',  # seconds
            'motion_timeout': '300',  # seconds (5 minutes)
            'default_screen': '0',
            'location': 'Rochester, NY',
            'temperature_unit': 'F',
        }
        
        for key, value in default_settings.items():
            if not Settings.query.filter_by(key=key).first():
                db.session.add(Settings(key=key, value=value))
        
        db.session.commit()
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
