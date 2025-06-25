import json
from datetime import datetime

# --- Data Loading ---
def load_data(filename):
    """Loads JSON data from a file."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # Return a default structure if user_preferences.json is not found
        if filename == 'user_preferences.json':
            return {"family_members": []}
        return {} 

vegetables_data = load_data('vegetables.json')
user_preferences = load_data('user_preferences.json')

# --- Helper Functions ---
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

def get_vegetable_list():
    """Returns a sorted list of all available vegetable names."""
    return sorted([veg["name"] for veg in vegetables_data])

# --- Agent Logic ---
def recommend_sabzi_for_family():
    """Recommends a dish based on present family members' common preferences and season."""
    if not user_preferences.get("family_members"):
        return "Sorry, no family member information found. Please add members using option '1'."

    all_members = [member["name"] for member in user_preferences["family_members"]]
    if not all_members:
        return "Please add family members first using option '1'."

    print("\nWho all are at home today? (Enter names separated by commas, e.g., Mom,Son)")
    print(f"Available members: {', '.join(all_members)}")
    
    present_members_input = input("Enter names of present members: ").split(',')
    present_members = [name.strip() for name in present_members_input]

    # Check if entered members exist
    invalid_members = [member for member in present_members if member not in all_members]
    if invalid_members:
        return f"Sorry, these names were not recognized: {', '.join(invalid_members)}. Please enter valid names."

    # Collect favorite vegetables for present members
    present_members_fav_veg = []
    for member_name in present_members:
        for member_info in user_preferences["family_members"]:
            if member_info["name"] == member_name:
                present_members_fav_veg.append(set(member_info["favorite_vegetables"]))
                break

    if not present_members_fav_veg:
        return "Could not find favorite vegetables for the present family members."

    # Find common favorite vegetables (intersection)
    # If there's only one member present, just use their favorites
    if len(present_members_fav_veg) == 1:
        common_fav_veg_set = present_members_fav_veg[0]
    else:
        common_fav_veg_set = set.intersection(*present_members_fav_veg)
    
    if not common_fav_veg_set:
        return "There are no common favorite vegetables among the present family members. Maybe try cooking something different for each?"

    current_season = get_current_season()
    seasonal_veg_names = get_seasonal_vegetables(current_season, vegetables_data)

    # Filter common and seasonal vegetables
    common_and_seasonal_veg = [
        veg_name for veg_name in common_fav_veg_set 
        if veg_name in seasonal_veg_names
    ]

    if not common_and_seasonal_veg:
        return f"Sorry, none of the common favorite vegetables ({', '.join(common_fav_veg_set)}) are available this season ({current_season})."

    suggestions = []
    for veg_name in common_and_seasonal_veg:
        for veg_info in vegetables_data:
            if veg_info["name"] == veg_name:
                if veg_info["dishes"]:
                    for dish in veg_info["dishes"]:
                        suggestions.append(f"Today, you can make {dish}.")
                else:
                    suggestions.append(f"Today, you can make {veg_name} Sabzi.")
                break
    
    if suggestions:
        unique_suggestions = list(set(suggestions)) # Remove duplicates
        if len(unique_suggestions) == 1:
            return unique_suggestions[0]
        else:
            return "Today, you can make (loved by everyone present):\n" + "\n".join(unique_suggestions)
    
    return "No specific dish recommendation found for today."

# --- Usage Example (Main Menu) ---
def main_menu():
    """Main function to run the Sabzi Recommender Agent."""
    print("Hello! Welcome to the Family Sabzi Recommender Agent.")
    while True:
        print("\n--- Menu ---")
        print("1. Set Family Members' Favorite Vegetables")
        print("2. What to Cook Today (based on family members)?")
        print("3. Exit")

        choice = input("Enter your choice: ")

        if choice == '1':
            print("\nEnter new member information or update existing member:")
            member_name = input("Enter member's name (e.g., Mom, Dad, Son): ").strip()
            
            # Display vegetable selection options
            available_veg = get_vegetable_list()
            print("\nPlease enter your favorite vegetables by their **numbers** or **names**, separated by commas (,).")
            print("Example: 1,3,5 or Potato,Spinach,Okra")
            
            for i, veg in enumerate(available_veg):
                print(f"{i+1}. {veg}")
            
            favs_input_raw = input("Enter your preferences: ").strip()
            favs_list = []
            
            # Process user input (numbers or names)
            input_parts = favs_input_raw.split(',')
            for part in input_parts:
                part = part.strip()
                if part.isdigit(): # If it's a number
                    index = int(part) - 1
                    if 0 <= index < len(available_veg):
                        favs_list.append(available_veg[index])
                    else:
                        print(f"Invalid number: {part}. Ignoring.")
                else: # If it's a name
                    if part in available_veg:
                        favs_list.append(part)
                    else:
                        print(f"Vegetable name not recognized: {part}. Ignoring.")

            favs_list = list(set(favs_list)) # Remove duplicates

            if not favs_list:
                print("No valid favorite vegetables selected.")
            else:
                # Check if member already exists
                found = False
                for member in user_preferences["family_members"]:
                    if member["name"] == member_name:
                        member["favorite_vegetables"] = favs_list
                        found = True
                        print(f"{member_name}'s favorite vegetables updated: {', '.join(favs_list)}")
                        break
                if not found:
                    user_preferences["family_members"].append({"name": member_name, "favorite_vegetables": favs_list})
                    print(f"{member_name} added to family and favorite vegetables saved: {', '.join(favs_list)}")
                
                with open('user_preferences.json', 'w', encoding='utf-8') as f:
                    json.dump(user_preferences, f, ensure_ascii=False, indent=2)
        
        elif choice == '2':
            print(recommend_sabzi_for_family())
        elif choice == '3':
            print("Thank you! See you next time.")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main_menu()