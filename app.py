import requests
from flask import Flask, render_template, request, redirect, session, url_for, flash
import json
from datetime import datetime, date

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# Load configuration from config.json
with open("config.json") as config_file:
    config = json.load(config_file)

# Determine the year based on config
YEAR = config.get("YEAR", 2024)
if YEAR == 2025:
    YEAR = "current"

# Load players dynamically from config
PLAYERS = config.get("PLAYERS", [])  # Default to an empty list if not specified

# Points based on F1's official scoring system for the top 10
F1_POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]

# Initialize scores and selections dynamically based on players
scores = {player: 0 for player in PLAYERS}
selected_drivers = {player: [] for player in PLAYERS}

# Caches for performance optimization
race_name_cache = {}
driver_points_cache = {}

# Function to fetch drivers for the current season
def fetch_drivers():
    """Fetch the list of drivers dynamically from Jolpica API."""
    url = f"http://api.jolpi.ca/ergast/f1/{YEAR}/drivers.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        drivers = [
            {"code": driver["code"], "name": f"{driver['givenName']} {driver['familyName']}"}
            for driver in data["MRData"]["DriverTable"]["Drivers"]
        ]
        return drivers
    except Exception as e:
        print(f"Error fetching drivers: {e}")
        return []

# Fetch race schedule
def fetch_race_schedule():
    """Fetch the full race schedule for the season from the API."""
    url = f"http://api.jolpi.ca/ergast/f1/{YEAR}.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        races = data['MRData']['RaceTable']['Races']
        
        # Collect weeks with their corresponding dates
        race_schedule = []
        for race in races:
            week = race['round']
            race_date = race['date']  # Race date
            race_schedule.append({"week": week, "date": race_date})
        
        return race_schedule
    except Exception as e:
        print(f"Error fetching race schedule: {e}")
        return []
    
def fetch_race_name(week):
    """Fetch the race name for a given week with caching."""
    # Return from cache if already stored
    if week in race_name_cache:
        return race_name_cache[week]

    # API call
    url = f"http://api.jolpi.ca/ergast/f1/{YEAR}/{week}/results.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # Debugging: Print response for investigation
        print(f"Race data for week {week}: {json.dumps(data, indent=2)}")

        # Extract race name
        races = data.get('MRData', {}).get('RaceTable', {}).get('Races', [])
        if races and 'raceName' in races[0]:
            race_name = races[0]['raceName']
            race_name_cache[week] = race_name  # Cache it
            return race_name

        # Log missing data
        print(f"No race found for week {week}.")
        race_name_cache[week] = "Race not found"
        return "Race not found"
    except Exception as e:
        print(f"Error fetching race name for week {week}: {e}")
        race_name_cache[week] = "Race not found"
        return "Race not found"
def fetch_driver_points(driver_code, week):
    """Fetch real driver points for a specific driver and week."""
    # Use cache if available
    if (driver_code, week) in driver_points_cache:
        return driver_points_cache[(driver_code, week)]

    # API call for race results
    url = f"http://api.jolpi.ca/ergast/f1/{YEAR}/{week}/results.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # Safely access data
        races = data.get('MRData', {}).get('RaceTable', {}).get('Races', [])
        if not races:
            print(f"No race data for week {week}.")
            driver_points_cache[(driver_code, week)] = 0
            return 0

        # Extract results
        results = races[0].get('Results', [])
        for idx, result in enumerate(results):
            if result['Driver']['code'] == driver_code:
                # Assign points based on F1 scoring system
                points = F1_POINTS[idx] if idx < len(F1_POINTS) else 0
                driver_points_cache[(driver_code, week)] = points
                return points

        # Log missing driver data
        print(f"Driver {driver_code} not found in week {week}.")
        driver_points_cache[(driver_code, week)] = 0
        return 0
    except Exception as e:
        print(f"Error fetching driver points for {driver_code} in week {week}: {e}")
        driver_points_cache[(driver_code, week)] = 0
        return 0


# Calculate available weeks
def get_available_weeks():
    """Calculate how many weeks are available based on today's date and the race schedule."""
    race_schedule = fetch_race_schedule()  # Get the schedule inside the function
    available_weeks = 0
    today = date.today()

    # Count the number of races that have either already occurred or are scheduled for today or in the future
    for race in race_schedule:
        race_date = datetime.strptime(race['date'], "%Y-%m-%d").date()
        if race_date <= today:
            available_weeks += 1
    
    return available_weeks


# On app start, fetch and print race data
race_schedule = fetch_race_schedule()
available_weeks = get_available_weeks()
print(f"Total number of races available: {len(race_schedule)}")
print(f"Number of races that have already passed: {available_weeks}")



@app.route("/")
def home():
    """Home page with navigation options."""
    user = session.get("user")
    completed_weeks = len(selected_drivers.get(user, []))
    return render_template("index.html", user=user, scores=scores, completed_weeks=completed_weeks)

@app.route("/select_user", methods=["GET", "POST"])
def select_user():
    """Allow the user to select a player dynamically."""
    if request.method == "POST":
        session["user"] = request.form["user"]
        return redirect(url_for("driver_selection"))
    return render_template("select_user.html", players=PLAYERS)


@app.route("/driver_selection", methods=["GET", "POST"])
def driver_selection():
    """Handle driver selection, ensuring picks are only allowed for past races."""
    user = session.get("user")
    if not user:
        return redirect(url_for("select_user"))

    # Determine the current week for this user
    current_week = len(selected_drivers[user]) + 1  # Next available week to pick
    drivers = fetch_drivers()  # Fetch drivers for the current season

    # Get the number of available weeks
    available_weeks = get_available_weeks()

    # Determine if picks are allowed
    allow_picks = current_week <= available_weeks

    # Handle form submission
    if request.method == "POST" and allow_picks:
        driver_code = request.form["driver"]
        selected_drivers[user].append(driver_code)
        return redirect(url_for("view_scores"))

    # Render the driver selection page
    return render_template(
        "driver_selection.html",
        current_week=current_week,
        drivers=drivers,
        allow_picks=allow_picks  # <-- Pass the allow_picks flag
    )





@app.route("/view_scores")
def view_scores():
    """Display scores dynamically for all players."""
    user = session.get("user")
    if not user:
        return redirect(url_for("select_user"))

    # Get the number of available weeks from the race schedule
    available_weeks = get_available_weeks()

    # Ensure completed_weeks does not exceed available_weeks
    completed_weeks = min(len(selected_drivers[user]), available_weeks)
    
    week_points = []

    # Calculate scores dynamically for each player
    player_points = {player: 0 for player in PLAYERS}
    for week in range(completed_weeks):
        race_name = fetch_race_name(week + 1)
        week_data = {"week": week + 1, "race_name": race_name}

        for player in PLAYERS:
            driver = selected_drivers[player][week] if week < len(selected_drivers[player]) else None
            points = fetch_driver_points(driver, week + 1) if driver else 0
            player_points[player] += points
            week_data[player] = {"driver": driver, "points": points}

        week_points.append(week_data)

    scores.update(player_points)

    return render_template(
        "scores.html",
        scores=scores,
        week_points=week_points,
        players=PLAYERS,
        player_points = player_points
    )

@app.route("/edit_selection", methods=["POST"])
def edit_selection():
    """Allow the user to edit a selected driver for a previous week."""
    user = request.form["user"]
    week = int(request.form["week"]) - 1  # Convert to 0-indexed week
    selected_driver = request.form.get("driver")

    if week < len(selected_drivers[user]):
        selected_drivers[user][week] = selected_driver
    return redirect(url_for("view_scores"))

if __name__ == "__main__":
    app.run(debug=True)
