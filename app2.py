from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime
import requests
import json
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Load configuration from JSON file
with open("config.json") as config_file:
    config = json.load(config_file)

YEAR = config["year"]
USERS_DB = {user["username"]: user for user in config["users"] if user["role"] == "Player"}
DB_PATH = "fantasy_f1.db"

F1_POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]

# Combined function to create the database and prefill the race rounds
def reset_database():
    # Open the database
    conn = sqlite3.connect('fantasy_f1.db')
    c = conn.cursor()

    # Drop the selections table if it exists to reset everything
    c.execute('''DROP TABLE IF EXISTS selections;''')
    c.execute('''DROP TABLE IF EXISTS driver_selections;''')
    conn.commit()
    print("Dropping old database table of races and user-driver selection tables if they existed.")
    # Recreate the selections table
    c.execute('''
        CREATE TABLE IF NOT EXISTS selections (
            username TEXT,
            race_round INTEGER,
            selected_driver TEXT,
            points INTEGER,
            PRIMARY KEY (username, race_round)
        )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS driver_selections (
        username TEXT,
        driver_code TEXT,
        selection_count INTEGER,
        PRIMARY KEY (username, driver_code)
    )
    ''')

    conn.commit()

    # Prefill race rounds with NULL values for selected_driver and points (structure only)
    races = fetch_race_schedule()  # Fetch race schedule

    for user in USERS_DB.keys():
        for race in races:
            c.execute('''
                INSERT OR IGNORE INTO selections (username, race_round, selected_driver, points)
                VALUES (?, ?, NULL, NULL)
            ''', (user, int(race["round"])))

    conn.commit()
    conn.close()
    print("Database reset complete with race rounds prefilled.")

def print_database_contents():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM selections')
    rows = c.fetchall()
    print("Database Contents (selections table):")
    for row in rows:
        print(row)
    conn.close()

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
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT driver_code, selection_count FROM driver_selections WHERE username = ?', (session["username"],))
        selection_counts = {row[0]: row[1] for row in c.fetchall()}
        conn.close()

        for driver in drivers:
            driver["selection_count"] = selection_counts.get(driver["code"], 0)

        return drivers
    except Exception as e:
        print(f"Error fetching drivers: {e}")
        return []

# Fetch and store race results for a specific round
def fetch_and_store_results(race_round, selected_driver):
    url = f"https://api.jolpi.ca/ergast/f1/{YEAR}/{race_round}/results.json"  # Updated URL
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # Look for the results for the specified round
        for result in data["MRData"]["RaceTable"]["Races"][0]["Results"]:  # Directly accessing the first (and only) race
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

                # Update the selections table with the points
                conn = sqlite3.connect('fantasy_f1.db')
                c = conn.cursor()
                c.execute("""
                    UPDATE selections
                    SET points = ?
                    WHERE race_round = ? AND selected_driver = ?
                """, (points, race_round, selected_driver))
                conn.commit()
                conn.close()
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
        conn = sqlite3.connect('fantasy_f1.db')
        c = conn.cursor()
        c.execute('SELECT selected_driver, points FROM selections WHERE username = ? AND race_round = ?', (username, race["round"]))
        selection = c.fetchone()

        # If a driver is selected and the race date is in the past, fetch the results and update points
        if selection and selection[0]:  # There is a driver selected
            race_date = datetime.strptime(race["date"], "%Y-%m-%d").date()
            if race_date < today and selection[1] is None:  # If race has passed but no points yet
                selected_driver = selection[0]
                fetch_and_store_results(race["round"], selected_driver)  # Update points in the database
                c.execute('SELECT points FROM selections WHERE username = ? AND race_round = ?', (username, race["round"]))
                updated_selection = c.fetchone()
                race["points"] = updated_selection[0] if updated_selection else None
            else:
                race["points"] = selection[1]  # Show the points if already updated

        conn.close()
        
        race["can_select_driver"] = race_date > today or selection is None or selection[0] is None  # Can select if race is in the future or no driver has been selected
        race["selected_driver"] = selection[0] if selection else None

    # Calculate scores from the database
    conn = sqlite3.connect('fantasy_f1.db')
    c = conn.cursor()
    c.execute('SELECT username, SUM(points) FROM selections GROUP BY username')
    scores_from_db = {row[0]: row[1] or 0 for row in c.fetchall()}
    conn.close()

    # Ensure scores have a value for all players
    all_users = USERS_DB.keys()  # Get all usernames from USERS_DB
    scores = {user: scores_from_db.get(user, 0) for user in all_users}

    
    print_database_contents()

    return render_template(
        "index.html",
        username=username,
        role=role,
        scores=scores,
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
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT selection_count FROM driver_selections WHERE username = ? AND driver_code = ?', (username, selected_driver))
        result = c.fetchone()
        selection_count = result[0] if result else 0

        if selection_count >= 2:
            return "You can only select each driver twice per season."

        # Update the selections table
        c.execute("""
            INSERT OR REPLACE INTO selections (username, race_round, selected_driver, points)
            VALUES (?, ?, ?, ?)
        """, (username, int(race_round), selected_driver, None))

        # Update the driver_selections table
        if result:
            c.execute('UPDATE driver_selections SET selection_count = selection_count + 1 WHERE username = ? AND driver_code = ?', (username, selected_driver))
        else:
            c.execute('INSERT INTO driver_selections (username, driver_code, selection_count) VALUES (?, ?, 1)', (username, selected_driver))

        conn.commit()
        conn.close()

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

    conn = sqlite3.connect('fantasy_f1.db')
    c = conn.cursor()
    c.execute('''
        SELECT username, race_round, selected_driver, points
        FROM selections
        ORDER BY username, race_round
    ''')
    selections = c.fetchall()
    conn.close()

    # Organize data by user
    user_data = {}
    for username, race_round, selected_driver, points in selections:
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

    return render_template("scores.html", user_data=user_data)

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
    app.run(host='0.0.0.0', port=5000,debug=True)
