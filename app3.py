from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime
import requests
import json
#import sqlite3
from supabase.client import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Supabase configuration
load_dotenv()
url = os.getenv("supabaseURL")  # Replace with your project URL**
key = os.getenv("supabaseKEY")  # Replace with your public anon key**
supabase: Client = create_client(url, key)  # Initialize Supabase client


# Load configuration from JSON file
with open("config.json") as config_file:
    config = json.load(config_file)

YEAR = config["year"]
USERS_DB = {user["username"]: user for user in config["users"] if user["role"] == "Player"}
#DB_PATH = "fantasy_f1.db" #commienting this out as I'm using a new database in Supabase

F1_POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]

# Combined function to create the database and prefill the race rounds
def reset_database():
    # Remove SQLite-specific code and replace with Supabase calls
    print("Resetting database...")  # Replace print statements with actual Supabase actions
    
    # Reset and prefill race rounds using Supabase
    races = fetch_race_schedule()  # Fetch race schedule

    # Use Supabase to delete all rows from the 'selections' table
    supabase.table("selections").delete().neq("username", "").execute()  # Delete selections table entries

    for user in USERS_DB.keys():
        for race in races:
            # Use Supabase to insert race selection data
            supabase.table("selections").insert({
                "username": user,
                "race_round": int(race["round"]),
                "selected_driver": None,
                "points": None
            }).execute()

    # Reset the 'driver_selections' table
    supabase.table("driver_selections").delete().neq("username", "").execute()  # Clear driver_selections table

    print("Database reset complete with race rounds prefilled.")


def print_database_contents():
    # Replace SQLite code with Supabase fetch and print the results from Supabase**
    selections = supabase.table("selections").select("*").execute().data
    print("Database Contents (selections table):")
    for row in selections:
        print(row)

# Fetch the race schedule
def fetch_race_schedule():
    url = f"https://api.jolpi.ca/ergast/f1/{YEAR}.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        races = [{"round": r["round"], "date": r["date"], "title": r["raceName"]} for r in data['MRData']['RaceTable']['Races']]
        return races
    except Exception as e:
        print(f"Error fetching race schedule: {e}")
        return []

# Fetch drivers for the season
def fetch_drivers():
    url = f"https://api.jolpi.ca/ergast/f1/{YEAR}/drivers.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        drivers = [{"code": d["code"], "name": f"{d['givenName']} {d['familyName']}"} for d in data["MRData"]["DriverTable"]["Drivers"]]

        # Fetch selection counts from the database
        # Replace SQLite query with Supabase query for driver selections**
        selections = supabase.table("driver_selections").select("*").eq("username", session["username"]).execute().data
        selection_counts = {row["driver_code"]: row["selection_count"] for row in selections}

        for driver in drivers:
            driver["selection_count"] = selection_counts.get(driver["code"], 0)

        return drivers
    except Exception as e:
        print(f"Error fetching drivers: {e}")
        return []

# Fetch and store race results for a specific round
def fetch_and_store_results(race_round, selected_driver):
    url = f"https://api.jolpi.ca/ergast/f1/{YEAR}/{race_round}/results.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        for result in data["MRData"]["RaceTable"]["Races"][0]["Results"]:
            if result["Driver"]["code"] == selected_driver:
                position = result.get("position")
                if position:
                    position = int(position)
                    if position <= len(F1_POINTS):
                        points = F1_POINTS[position - 1]
                    else:
                        points = None
                else:
                    points = None

                # Use Supabase to update the selections table with points**
                supabase.table("selections").update({"points": points}).eq("race_round", race_round).eq("selected_driver", selected_driver).execute()
                break
    except Exception as e:
        print(f"Error fetching and storing race results for round {race_round}: {e}")


@app.route('/')
def home():
    if "username" not in session:
        return redirect(url_for("login"))
    
    username = session["username"]
    role = USERS_DB[username]["role"]

    # Fetch the races and results
    races = fetch_race_schedule()

    # Get today's date
    today = datetime.today().date()

    # Find the current race round (based on today's date)
    current_round = None
    for race in races:
        race_date = datetime.strptime(race["date"], "%Y-%m-%d").date()
        if race_date >= today:  # Identify the current or next race
            current_round = race["round"]
            break

    # Add "YOU ARE HERE" dynamically into the race schedule
    you_are_here_inserted = False
    for i, race in enumerate(races):
        race_date = datetime.strptime(race["date"], "%Y-%m-%d").date()
        if race_date >= today and not you_are_here_inserted:
            races.insert(i, {
                "round": None,
                "title": "YOU ARE HERE",
                "date": today.strftime("%Y-%m-%d"),
                "you_are_here": True,
            })
            you_are_here_inserted = True
            break
    if not you_are_here_inserted:
        races.append({
            "round": None,
            "title": "YOU ARE HERE",
            "date": today.strftime("%Y-%m-%d"),
            "you_are_here": True,
        })

    # Check race selection status and points
    for race in races:
        if race.get("you_are_here"):  # Skip processing for "YOU ARE HERE"
            race["can_select_driver"] = False
            race["selected_driver"] = None
            race["points"] = None
            continue


        # Check if the user has already selected a driver for this race
        # Fetch selections data from Supabase instead of SQLite**
        selection = supabase.table("selections").select("selected_driver, points").eq("username", username).eq("race_round", race["round"]).execute().data

        # If a driver is selected and the race date is in the past, fetch the results and update points
        if selection and selection[0]["selected_driver"]:  # There is a driver selected
            race_date = datetime.strptime(race["date"], "%Y-%m-%d").date()
            if race_date < today and selection[0]["points"] is None:
                selected_driver = selection[0]["selected_driver"]
                fetch_and_store_results(race["round"], selected_driver)
                updated_selection = supabase.table("selections").select("points").eq("username", username).eq("race_round", race["round"]).execute().data
                race["points"] = updated_selection[0]["points"] if updated_selection else None
            else:
                race["points"] = selection[0]["points"] # Show the points if already updated

        #conn.close()
        
        race["can_select_driver"] = race_date > today or selection is None or selection[0]["selected_driver"] is None  # Can select if race is in the future or no driver has been selected
        race["selected_driver"] = selection[0]["selected_driver"] if selection else None

    # Calculate scores from Supabase
    #scores_from_db = supabase.table("selections").select("username, SUM(points)").group_by("username").execute().data
    #scores_from_db = supabase.rpc("get_user_scores").execute().data #replaced since Supabase doesn't use groupby?
    #disabling above bc rbc requires RLS and I don't get how to do this
    # Get data from Supabase
    data = supabase.table("selections").select("username", "points").execute().data

    # Aggregate scores in Python
    from collections import defaultdict

    scores = defaultdict(int)
    for row in data:
        if row["points"] is not None:  # Ensure there's no None value for points
            scores[row["username"]] += row["points"]

    # Transform scores into a list of dictionaries
    scores_from_db = [{"username": user, "total_points": points} for user, points in scores.items()]

    # Create a dictionary from the scores_from_db
    scores_dict = {row["username"]: row["total_points"] for row in scores_from_db}

    # Ensure scores have a value for all players
    all_users = USERS_DB.keys()  # Get all usernames from USERS_DB
    scores = {user: scores_dict.get(user, 0) for user in all_users}
    # Sort the dictionary by points in descending order
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    
    print_database_contents()
# In your home function, for each race, format the date:
    for race in races:
        race_date = datetime.strptime(race["date"], "%Y-%m-%d").date()  # Parse the date
        race["formatted_date"] = race_date.strftime("%m/%d/%Y")  # Format the date to MM/DD/YYYY
    return render_template(
        "index.html",
        username=username,
        role=role,
        sorted_scores=sorted_scores,
        races=races,
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check if username exists and password matches
        if username in USERS_DB and USERS_DB[username]['password'] == password:
            session['username'] = username
            return redirect(url_for('home'))
        else:
            return "Invalid credentials. Please try again."

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/select_driver', methods=['GET', 'POST'])
def select_driver():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    race_round = request.args.get('race_round')  # Get the race round from the URL

    if request.method == 'POST':
        selected_driver = request.form['driver']

        # Check if the driver has already been selected twice
        selection = supabase.table("driver_selections").select("selection_count").eq("username", username).eq("driver_code", selected_driver).execute().data

        selection_count = selection[0]["selection_count"] if selection else 0

        if selection_count >= 2:
            return "You can only select each driver twice per season."

        # Check if the selection for the given race round already exists
        existing_selection = supabase.table("selections").select("id").eq("username", username).eq("race_round", int(race_round)).execute().data

        if existing_selection:  # If the selection exists, update the existing row
            supabase.table("selections").update({
                "selected_driver": selected_driver,
                "points": None  # Set points to None or update with actual points if available
            }).eq("username", username).eq("race_round", int(race_round)).execute()
        else:  # Otherwise, insert a new row
            supabase.table("selections").insert({
                "username": username,
                "race_round": int(race_round),
                "selected_driver": selected_driver,
                "points": None  # Set points to None or update with actual points if available
            }).execute()

        # Update the driver_selections table
        if selection:
            # Fetch the current selection_count from the existing selection
            current_count = selection[0]["selection_count"] if selection else 0

            # Increment selection_count and update the table
            supabase.table("driver_selections").update({
                "selection_count": current_count + 1
            }).eq("username", username).eq("driver_code", selected_driver).execute()
        else:
            # Insert a new record if no selection exists
            supabase.table("driver_selections").insert({
                "username": username,
                "driver_code": selected_driver,
                "selection_count": 1
            }).execute()

        return redirect(url_for('home'))

    # Fetch available drivers for the season
    drivers = fetch_drivers()
    # Fetch the race schedule and find the race title
    race = next((r for r in fetch_race_schedule() if int(r["round"]) == int(race_round)), None)
    race_title = race["title"] if race else "Unknown Race"

    return render_template('select_driver.html', username=username, race_round=race_round, race_title=race_title, drivers=drivers)
   
@app.route('/scores')
def scores_view():
    if "username" not in session:
        return redirect(url_for("login"))

    # Fetch selections from Supabase
    selections = supabase.table("selections").select("username, race_round, selected_driver, points").execute().data

    # Sort selections by race round numerically
    selections.sort(key=lambda x: x['race_round'])

    user_data = {}
    for selection in selections:
        username, race_round, selected_driver, points = selection["username"], selection["race_round"], selection["selected_driver"], selection["points"]
        if username not in user_data:
            user_data[username] = {
                "selections": [],
                "total_points": 0
            }
        user_data[username]["selections"].append({
            "race_round": race_round,
            "selected_driver": selected_driver,
            "points": points
        })
        if points is not None:
            user_data[username]["total_points"] += points
    # Fetch race schedule (you could adjust this to your actual race fetching method)
    races = fetch_race_schedule()  # Adjust to your fetching logic

    return render_template("scores.html", user_data=user_data, races=races)


@app.route('/chart_data')
def chart_data():
    if "username" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    # Fetch data from Supabase
    selections = supabase.table("selections").select("username, race_round, points").execute().data

    # Process data into a dictionary
    user_scores = {}
    for row in selections:
        username, race_round, points = row["username"], row["race_round"], row["points"]
        if username not in user_scores:
            user_scores[username] = []

        user_scores[username].append({"race_round": race_round, "points": points or 0})  # Use 0 if points are None

    # Sort each user's data by race_round and calculate cumulative points
    for username, data in user_scores.items():
        sorted_data = sorted(data, key=lambda x: x["race_round"])
        cumulative_points = 0
        race_rounds = []
        points = []
        for entry in sorted_data:
            cumulative_points += entry["points"]
            race_rounds.append(entry["race_round"])
            points.append(cumulative_points)
        user_scores[username] = {"race_rounds": race_rounds, "points": points}

    return jsonify(user_scores)






if __name__ == '__main__':
    import argparse

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Fantasy F1 App')
    parser.add_argument('--reset-db', action='store_true', help='Reset the database')
    args = parser.parse_args()

    # Call reset_database only if --reset-db is provided
    if args.reset_db:
        reset_database()
    else:
        print("Starting app without resetting the database...")

    # Start the app regardless of the reset flag
    #app.run(debug=True)
    #For running on Render require
    app.run(host='0.0.0.0', port=5000,debug=True)