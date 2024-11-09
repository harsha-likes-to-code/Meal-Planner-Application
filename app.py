from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import random
from datetime import datetime
import requests
from bson import ObjectId  # Import this to handle ObjectId for MongoDB

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client.mealplanner_db
users_collection = db.users
recipes_collection = db.recipes
meal_plans_collection = db.meal_plans

# API Key for recipe suggester
API_KEY = '528a5c84d4764b438f9bb87504d13332'  # Replace with actual API key

# Meal Planner functions
def generate_meal_plan(user_preferences, duration='weekly'):
    user_id = ObjectId(session['user_id'])  # Get the logged-in user's ID

    plan = {'start_date': datetime.now(), 'duration': duration, 'meals': [], 'user_id': user_id}
    days = 7 if duration == 'weekly' else 30 if duration == 'monthly' else 1

    for _ in range(days):
        recipes = list(recipes_collection.find(user_preferences))
        if recipes:
            daily_meal = random.choice(recipes)
            plan['meals'].append(daily_meal)

    if plan['meals']:  # If meals were added
        meal_plan_id = meal_plans_collection.insert_one(plan).inserted_id
        return meal_plan_id
    else:
        return None

def get_meal_plan(meal_plan_id):
    return meal_plans_collection.find_one({'_id': ObjectId(meal_plan_id)})

def customize_meal_plan(meal_plan_id, new_servings=None, substitute_ingredient=None):
    meal_plan = meal_plans_collection.find_one({'_id': ObjectId(meal_plan_id)})

    if new_servings:
        for meal in meal_plan['meals']:
            meal['servings'] = new_servings

    if substitute_ingredient:
        for meal in meal_plan['meals']:
            for ingredient in meal['ingredients']:
                if ingredient['name'] == substitute_ingredient['name']:
                    ingredient.update(substitute_ingredient)

    meal_plans_collection.update_one({'_id': ObjectId(meal_plan_id)}, {'$set': meal_plan})
    return meal_plan

# Recipe Suggester functions
def fetch_recipe_data(query_params):
    url = f"https://api.spoonacular.com/recipes/complexSearch?{query_params}&apiKey={API_KEY}"
    response = requests.get(url)
    data = response.json()
    return data['results']

def store_recipes(recipes):
    for recipe in recipes:
        if not recipes_collection.find_one({'id': recipe['id']}):
            recipes_collection.insert_one(recipe)

def suggest_recipes(user_preferences):
    query_params = '&'.join([f'{k}={v}' for k, v in user_preferences.items()])
    recipes = fetch_recipe_data(query_params)
    store_recipes(recipes)
    return recipes

# Home route: Displays the dashboard if logged in, otherwise redirects to login or registration page
@app.route('/')
def home():
    if 'user_id' in session:
        return render_template('dashboard.html')
    return redirect(url_for('login'))

# User Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        if users_collection.find_one({'email': email}):
            flash('User with this email already exists!', 'error')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        user_data = {'name': name, 'email': email, 'password': hashed_password}
        users_collection.insert_one(user_data)
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# User Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = users_collection.find_one({'email': email})

        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password.', 'error')

    return render_template('login.html')

# Dashboard
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

# Logout
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))

# Profile Route: Allows users to view and update their profile
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Fetch the user's profile from the database
    user = users_collection.find_one({'_id': ObjectId(session['user_id'])})

    if request.method == 'POST':
        # Get updated data from the form
        updated_name = request.form['name']
        updated_dietary_preferences = request.form['dietary_preferences']
        updated_restrictions = request.form['restrictions']

        # Update the user's profile in the database
        users_collection.update_one(
            {'_id': ObjectId(session['user_id'])},
            {'$set': {
                'name': updated_name,
                'dietary_preferences': updated_dietary_preferences,
                'restrictions': updated_restrictions
            }}
        )

        flash('Profile updated successfully!', 'success')

        # Redirect to the meal plan creation page after updating the profile
        return redirect(url_for('meal_plans'))

    return render_template('profile.html', user=user)

# Meal Plans Route: Displays or manages meal plans
# Meal Plans Route: Displays or manages meal plans
@app.route('/meal_plans', methods=['GET', 'POST'])
def meal_plans():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # If the method is GET, display the meal plans
    if request.method == 'GET':
        # Fetch meal plans for the logged-in user
        user_id = ObjectId(session['user_id'])
        meal_plans = meal_plans_collection.find({'user_id': user_id})

        return render_template('meal_plans.html', meal_plans=meal_plans)

    # If the method is POST, handle form submissions for creating or updating meal plans
    if request.method == 'POST':
        # Handle the creation or update of meal plans based on form data
        user_preferences = request.form.get('preferences')  # Example: Get preferences from form
        duration = request.form.get('duration', 'weekly')  # Default to 'weekly'

        # Generate a new meal plan based on the user's preferences
        meal_plan_id = generate_meal_plan({'preferences': user_preferences}, duration)
        flash('Meal plan created successfully!', 'success')
        return redirect(url_for('meal_plans'))

@app.route('/view_meal_plan/<meal_plan_id>', methods=['GET'])
def view_meal_plan(meal_plan_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Fetch the meal plan from the database by its ID
    meal_plan = meal_plans_collection.find_one({'_id': ObjectId(meal_plan_id)})

    if meal_plan:
        return render_template('view_meal_plan.html', meal_plan=meal_plan)
    else:
        flash('Meal plan not found!', 'error')
        return redirect(url_for('meal_plans'))

# Generate Meal Plan
def generate_meal_plan(user_preferences, duration='weekly'):
    user_id = ObjectId(session['user_id'])  # Get the logged-in user's ID

    plan = {'start_date': datetime.now(), 'duration': duration, 'meals': [], 'user_id': user_id}
    days = 7 if duration == 'weekly' else 30 if duration == 'monthly' else 1

    for _ in range(days):
        recipes = list(recipes_collection.find(user_preferences))
        if recipes:
            daily_meal = random.choice(recipes)
            plan['meals'].append(daily_meal)

    if plan['meals']:  # If meals were added
        meal_plan_id = meal_plans_collection.insert_one(plan).inserted_id
        return meal_plan_id
    else:
        return None

if __name__ == '__main__':
    app.run(debug=True)




