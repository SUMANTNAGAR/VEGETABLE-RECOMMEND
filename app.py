import json
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template # Import Flask, request, and jsonify for API
from flask_cors import CORS # Import CORS for cross-origin requests
import re

app = Flask(__name__)
CORS(app) # Enable CORS for all routes, important for web apps

# --- Data Loading (Same as before) ---
def load_data(filename, default_value=None):
    """Loads JSON data from a file, with a default value if not found."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default_value if default_value is not None else {}

vegetables_data = load_data('vegetables.json', default_value=[])
dishes_data = load_data('dishes.json', default_value=[])
user_preferences = load_data('user_preferences.json', default_value={"family_members": []})

# --- Helper Functions (Same as before) ---
def get_current_season():
    """Determines the current season based on the month (for Ahmedabad, Gujarat)."""
    month = datetime.now().month
    if 3 <= month <= 6:  # March to June
        return "summer"
    elif 7 <= month <= 9: # July to September
        return "monsoon"
    elif 10 <= month <= 11: # October to November
        return "autumn"
    else: # December, January, February
        return "winter"

def get_seasonal_vegetables(current_season, all_vegetables_data):
    """Returns a list of vegetable names available in the current season."""
    seasonal_veg_names = []
    for veg in all_vegetables_data:
        if "year-round" in veg["seasonal"] or current_season in veg["seasonal"]:
            seasonal_veg_names.append(veg["name"])
    return seasonal_veg_names

def normalize_ingredient_name(name):
    """Normalize ingredient names for smart matching (case-insensitive, ignore brackets, Hindi/English, etc.)"""
    # Lowercase
    name = name.lower()
    # Remove anything in brackets and the brackets themselves
    name = re.sub(r'\([^)]*\)', '', name)
    # Remove extra spaces and special characters
    name = re.sub(r'[^\w\u0900-\u097F]+', ' ', name)  # keep Hindi chars
    name = name.strip()
    return name

# --- API Endpoints ---

@app.route('/api/vegetables', methods=['GET'])
def api_get_all_vegetables():
    """API endpoint to get all available vegetable names."""
    return jsonify(sorted([veg["name"] for veg in vegetables_data]))

@app.route('/api/family_members', methods=['GET'])
def api_get_family_members():
    """API endpoint to get all family members data."""
    # Reload preferences to ensure latest data is sent
    global user_preferences
    user_preferences = load_data('user_preferences.json', default_value={"family_members": []})
    return jsonify(user_preferences)

@app.route('/api/set_preferences', methods=['POST'])
def api_set_preferences():
    """API endpoint to add/update family member preferences."""
    data = request.get_json()
    member_name = data.get('member_name')
    favorite_vegetables = data.get('favorite_vegetables')

    if not member_name or not favorite_vegetables:
        return jsonify({"status": "error", "message": "Member name and favorite vegetables are required."}), 400

    # Ensure vegetables are valid (optional, but good practice)
    all_valid_veg = [veg["name"] for veg in vegetables_data]
    for veg in favorite_vegetables:
        if veg not in all_valid_veg:
            return jsonify({"status": "error", "message": f"Invalid vegetable: '{veg}'"}), 400

    found = False
    for member in user_preferences["family_members"]:
        if member["name"].lower() == member_name.lower(): # Case-insensitive check
            member["name"] = member_name # Keep original casing if user provides different
            member["favorite_vegetables"] = favorite_vegetables
            found = True
            message = f"'{member_name}'s' favorite vegetables updated successfully!"
            break
    if not found:
        # Check if name already exists (for new members)
        existing_names = [member["name"].lower() for member in user_preferences["family_members"]]
        if member_name.lower() in existing_names:
            return jsonify({"status": "error", "message": f"'{member_name}' already exists. Please use a different name or update the existing member."}), 400
        
        user_preferences["family_members"].append({"name": member_name, "favorite_vegetables": favorite_vegetables})
        message = f"New member '{member_name}' added with favorite vegetables."

    with open('user_preferences.json', 'w', encoding='utf-8') as f:
        json.dump(user_preferences, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "success", "message": message})

@app.route('/api/recommend_sabzi', methods=['POST'])
def api_recommend_sabzi():
    """API endpoint to get sabzi recommendation (smarter logic)."""
    data = request.get_json()
    present_members = data.get('present_members')

    if not present_members:
        return jsonify({"status": "error", "message": "Please specify which members are present today."}), 400

    if not user_preferences.get("family_members"):
        return jsonify({"status": "error", "message": "Sorry, no family member information found. Please add members first."}), 400

    all_registered_members = [member["name"] for member in user_preferences["family_members"]]
    invalid_members = [member for member in present_members if member not in all_registered_members]
    if invalid_members:
        return jsonify({"status": "error", "message": f"Sorry, these names were not recognized: {', '.join(invalid_members)}. Please select valid members."}), 400

    present_members_fav_veg = []
    for member_name in present_members:
        for member_info in user_preferences["family_members"]:
            if member_info["name"] == member_name:
                present_members_fav_veg.append(set(member_info["favorite_vegetables"]))
                break

    if not present_members_fav_veg:
        return jsonify({"status": "error", "message": "Could not find favorite vegetables for the present family members."}), 400

    if len(present_members_fav_veg) == 1:
        common_fav_veg_set = present_members_fav_veg[0]
    else:
        common_fav_veg_set = set.intersection(*present_members_fav_veg)

    if not common_fav_veg_set:
        return jsonify({"status": "warning", "message": "There are no common favorite vegetables among the present family members. Maybe try cooking something different for each?"}), 200

    current_season = get_current_season()
    seasonal_veg_names = get_seasonal_vegetables(current_season, vegetables_data)
    available_and_preferred_veg = common_fav_veg_set.intersection(set(seasonal_veg_names))

    # SMARTER LOGIC: Allow common sabzi ingredients
    common_sabzi_ingredients = set([
        "Onion (प्याज)", "Tomato (टमाटर)", "Ginger (अदरक)", "Garlic (लहसुन)",
        "Green Chili (हरी मिर्च)", "Coriander Leaves (हरा धनिया)", "Mint (पुदीना)",
        "Curry Leaves (करी पत्ता)", "Capsicum (शिमला मिर्च)"
    ])
    # Normalize all ingredient names for matching
    normalized_common = set(normalize_ingredient_name(x) for x in common_sabzi_ingredients)
    normalized_available_and_preferred_veg = set(normalize_ingredient_name(x) for x in available_and_preferred_veg)
    possible_dishes = []
    for dish_info in dishes_data:
        dish_name = dish_info["name"]
        dish_ingredients = set(dish_info["ingredients"])
        if not dish_ingredients:
            continue
        normalized_ingredients = set(normalize_ingredient_name(x) for x in dish_ingredients)
        # Get non-common ingredients (the main vegetables/ingredients)
        main_ingredients = normalized_ingredients - normalized_common
        # Check if ANY of the main ingredients are in user's favorites
        if any(ing in normalized_available_and_preferred_veg for ing in main_ingredients):
            # For remaining ingredients, they should either be in favorites or be common ingredients
            remaining_ingredients = normalized_ingredients - normalized_available_and_preferred_veg
            if all(ing in normalized_common for ing in remaining_ingredients):
                possible_dishes.append(f"Today, you can make {dish_name}.")

    if possible_dishes:
        unique_suggestions = sorted(list(set(possible_dishes)))
        if len(unique_suggestions) == 1:
            return jsonify({"status": "success", "recommendation": unique_suggestions[0]}), 200
        else:
            return jsonify({"status": "success", "recommendation": "Today, you can make (loved by everyone present):\n" + "\n".join(unique_suggestions)}), 200

    return jsonify({"status": "info", "message": "No specific dish recommendation found for today from the available options. Consider adding more favorite vegetables or check if more dishes can be made from current common vegetables."}), 200

@app.route('/api/seasonal_vegetables', methods=['GET'])
def api_get_seasonal_vegetables():
    """API endpoint to get all vegetable names available in the current season (market), excluding non-vegetables like dudh, makhan, nariyal, etc."""
    current_season = get_current_season()
    seasonal_veg_names = get_seasonal_vegetables(current_season, vegetables_data)
    # List of non-vegetable items to exclude (add more as needed)
    non_veg_items = [
        'Paneer', 'पनीर', 'Rabodi', 'राबोड़ी', 'Vadi', 'वादी', 'Papad', 'पापड़', 'Khichiya', 'खिचीया',
        'Cashews', 'काजू', 'Cream', 'मलाई', 'Butter', 'मक्खन', 'Curd', 'दही', 'Gram Flour', 'बेसन',
        'Coconut', 'नारियल', 'Poppy Seeds', 'खसखस', 'Ghee', 'घी', 'Coconut Milk', 'नारियल का दूध',
        'Pickle Masala', 'अचार मसाला', 'Red Chili', 'लाल मिर्च', 'Black Pepper', 'काली मिर्च',
        'Yellow Peas', 'पीली मटर', 'Red Lentil', 'मसूर दाल', 'Green Gram', 'Moong Dal', 'मूंग दाल',
        'Kidney Beans', 'राजमा', 'Black Chickpeas', 'काला चना', 'Pigeon Pea', 'Toor Dal', 'अरहर दाल',
        'Black Gram', 'Urad Dal', 'उड़द दाल', 'Split Chickpeas', 'चना दाल', 'Black-eyed Peas', 'लोबिया दाल',
        'Horse Gram', 'कुल्थी दाल', 'Peas (Dried/Split)', 'मटर - सूखे/फटे', 'Soybean', 'सोयाबीन',
        'Split Yellow Moong Dal', 'पीली मूंग दाल', 'Chickpeas', 'Garbanzo Beans', 'काबुली चना',
        'Moth Bean', 'मोठ दाल', 'Khesari Dal', 'खेसरी दाल', 'Guar (Dal)', 'गौर - दाल'
    ]
    def is_veg(name):
        for item in non_veg_items:
            if item.lower() in name.lower():
                return False
        return True
    filtered_veg = [veg for veg in seasonal_veg_names if is_veg(veg)]
    return jsonify(sorted(filtered_veg))

@app.route('/')
def serve_index():
    return render_template('index.html')

if __name__ == '__main__':
    # Make sure vegetables.json, dishes.json, user_preferences.json are in the same directory
    # To run this:
    # 1. pip install Flask Flask-Cors
    # 2. python app.py
    # This will run on http://127.0.0.1:5000/
    app.run(host='0.0.0.0', port=5000, debug=True) # debug=True is good for development, turn off for production