import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file, render_template # Import Flask, request, and jsonify for API
from flask_cors import CORS # Import CORS for cross-origin requests
import re
from flask_login import login_required, current_user, LoginManager, login_user, logout_user, UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'my_dev_secret_key_12345'
CORS(app) # Enable CORS for all routes, important for web apps

# Add database URI config for SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'

# Initialize Flask extensions (if not already done)
login_manager = LoginManager(app)
mail = Mail(app)

db = SQLAlchemy(app)

# Add FamilyMember model above its first use
class FamilyMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    favorite_vegetables = db.Column(db.PickleType, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __init__(self, name, favorite_vegetables, user_id):
        self.name = name
        self.favorite_vegetables = favorite_vegetables
        self.user_id = user_id

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    mobile_number = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    otp = db.Column(db.String(6))
    otp_expiry = db.Column(db.DateTime)
    family_members = db.relationship('FamilyMember', backref='user', lazy=True)

    def __init__(self, mobile_number, email, password_hash):
        self.mobile_number = mobile_number
        self.email = email
        self.password_hash = password_hash

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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
@login_required
def api_get_family_members():
    members = FamilyMember.query.filter_by(user_id=current_user.id).all()
    return jsonify({
        "family_members": [
            {
                "name": m.name,
                "favorite_vegetables": m.favorite_vegetables
            } for m in members
        ]
    })

@app.route('/api/set_preferences', methods=['POST'])
@login_required
def api_set_preferences():
    data = request.get_json()
    member_name = data.get('member_name')
    favorite_vegetables = data.get('favorite_vegetables')

    if not member_name or not favorite_vegetables:
        return jsonify({"status": "error", "message": "Member name and favorite vegetables are required."}), 400

    all_valid_veg = [veg["name"] for veg in vegetables_data]
    for veg in favorite_vegetables:
        if veg not in all_valid_veg:
            return jsonify({"status": "error", "message": f"Invalid vegetable: '{veg}'"}), 400

    member = FamilyMember.query.filter_by(user_id=current_user.id, name=member_name).first()
    if member:
        member.favorite_vegetables = favorite_vegetables
        message = f"'{member_name}'s' favorite vegetables updated successfully!" # <-- अब सही इंडेंटेशन
    else:
        member = FamilyMember(name=member_name, favorite_vegetables=favorite_vegetables, user_id=current_user.id)
        db.session.add(member)
        message = f"New member '{member_name}' added with favorite vegetables."
    db.session.commit()
    return jsonify({"status": "success", "message": message})

@app.route('/api/recommend_sabzi', methods=['POST'])
@login_required
def api_recommend_sabzi():
    data = request.get_json()
    present_members = data.get('present_members')

    if not present_members:
        return jsonify({"status": "error", "message": "Please specify which members are present today."}), 400

    members = FamilyMember.query.filter_by(user_id=current_user.id).all()
    if not members:
        return jsonify({"status": "error", "message": "Sorry, no family member information found. Please add members first."}), 400

    all_registered_members = [member.name for member in members]
    invalid_members = [member for member in present_members if member not in all_registered_members]
    if invalid_members:
        return jsonify({"status": "error", "message": f"Sorry, these names were not recognized: {', '.join(invalid_members)}. Please select valid members."}), 400

    present_members_fav_veg = []
    for member_name in present_members:
        for member_info in members:
            if member_info.name == member_name:
                present_members_fav_veg.append(set(member_info.favorite_vegetables))
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
    normalized_common = set(normalize_ingredient_name(x) for x in common_sabzi_ingredients)
    normalized_available_and_preferred_veg = set(normalize_ingredient_name(x) for x in available_and_preferred_veg)
    possible_dishes = []
    for dish_info in dishes_data:
        dish_name = dish_info["name"]
        dish_ingredients = set(dish_info["ingredients"])
        if not dish_ingredients:
            continue
        normalized_ingredients = set(normalize_ingredient_name(x) for x in dish_ingredients)
        main_ingredients = normalized_ingredients - normalized_common
        if any(ing in normalized_available_and_preferred_veg for ing in main_ingredients):
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

@app.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    return jsonify({
        "mobile_number": current_user.mobile_number,
        "email": current_user.email
    }), 200

@app.route('/api/update_profile', methods=['POST'])
@login_required
def update_profile():
    data = request.get_json()
    new_mobile = data.get('mobile_number')
    new_email = data.get('email')

    # Validate email format
    if new_email and not re.match(r"[^@]+@[^@]+\.[^@]+", new_email):
        return jsonify({"status": "error", "message": "Invalid email format."}), 400

    # Validate mobile number (example: 10 digits)
    if new_mobile and not re.match(r"^[0-9]{10}$", new_mobile):
        return jsonify({"status": "error", "message": "Invalid mobile number format."}), 400

    # Check uniqueness for email
    if new_email and new_email != current_user.email:
        existing = User.query.filter_by(email=new_email).first()
        if existing:
            return jsonify({"status": "error", "message": "Email already in use."}), 400
        current_user.email = new_email

    # Check uniqueness for mobile number
    if new_mobile and new_mobile != current_user.mobile_number:
        existing = User.query.filter_by(mobile_number=new_mobile).first()
        if existing:
            return jsonify({"status": "error", "message": "Mobile number already in use."}), 400
        current_user.mobile_number = new_mobile

    # Save changes
    db.session.commit()
    return jsonify({"status": "success", "message": "Profile updated successfully."}), 200

@app.route('/')
def serve_index():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    mobile = data.get('mobile_number')
    email = data.get('email')
    password = data.get('password')

    if not mobile or not email or not password:
        return jsonify({'status': 'error', 'message': 'All fields required.'}), 400

    if User.query.filter((User.mobile_number == mobile) | (User.email == email)).first():
        return jsonify({'status': 'error', 'message': 'Mobile or email already registered.'}), 400

    user = User(
        mobile_number=mobile,
        email=email,
        password_hash=generate_password_hash(password)
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Registration successful.'}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    mobile = data.get('mobile_number')
    password = data.get('password')
    user = User.query.filter_by(mobile_number=mobile).first()
    if user and check_password_hash(user.password_hash, password):
        login_user(user)
        return jsonify({'status': 'success', 'message': 'Login successful.'}), 200
    return jsonify({'status': 'error', 'message': 'Invalid credentials.'}), 401

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'status': 'success', 'message': 'Logged out.'}), 200

def send_otp_email(email, otp):
    msg = Message('Your OTP Code', sender='noreply@yourdomain.com', recipients=[email])
    msg.body = f'Your OTP code is: {otp}'
    mail.send(msg)

@app.route('/forgot_password_request', methods=['POST'])
def forgot_password_request():
    data = request.get_json()
    email = data.get('email')
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'status': 'error', 'message': 'Email not found.'}), 404
    otp = str(random.randint(100000, 999999))
    user.otp = otp
    user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
    db.session.commit()
    send_otp_email(email, otp)
    return jsonify({'status': 'success', 'message': 'OTP sent to email.'}), 200

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    user = User.query.filter_by(email=email).first()
    if not user or user.otp != otp or user.otp_expiry < datetime.utcnow():
        return jsonify({'status': 'error', 'message': 'Invalid or expired OTP.'}), 400
    return jsonify({'status': 'success', 'message': 'OTP verified.'}), 200

@app.route('/reset_password', methods=['POST'])
def reset_password():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    new_password = data.get('new_password')
    user = User.query.filter_by(email=email).first()
    if not user or user.otp != otp or user.otp_expiry < datetime.utcnow():
        return jsonify({'status': 'error', 'message': 'Invalid or expired OTP.'}), 400
    user.password_hash = generate_password_hash(new_password)
    user.otp = None
    user.otp_expiry = None
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Password reset successful.'}), 200

if __name__ == '__main__':
    # Make sure vegetables.json, dishes.json, user_preferences.json are in the same directory
    # To run this:
    # 1. pip install Flask Flask-Cors
    # 2. python app.py
    # This will run on http://127.0.0.1:5000/
    app.run(host='0.0.0.0', port=5000, debug=True) # debug=True is good for development, turn off for production