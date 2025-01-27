import time
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from supabase.client import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

# Supabase configuration
load_dotenv()
url = os.getenv("supabaseURL")  # Replace with your project URL**
key = os.getenv("supabaseKEY")  # Replace with your public anon key**
supabase: Client = create_client(url, key)  # Initialize Supabase client

CACHE_EXPIRY = timedelta(days=30)  # Cache duration


# Fetch constructor (team) info for a driver in a specific season
def fetch_constructor(driver_id, year):
    constructor_url = f"https://api.jolpi.ca/ergast/f1/{year}/drivers/{driver_id}/constructors.json"
    try:
        response = requests.get(constructor_url)
        response.raise_for_status()
        constructor_data = response.json()

        # Get the first constructor (most recent/current one)
        constructor = constructor_data["MRData"]["ConstructorTable"]["Constructors"][0]
        return {
            "name": constructor["name"],
            "wikipedia_url": constructor["url"],
        }
    except Exception as e:
        print(f"Error fetching constructor for {driver_id} in {year}: {e}")
        return {"name": "Unknown", "wikipedia_url": None}


# Fetch team logo from Wikipedia
def fetch_logo_from_wikipedia(wikipedia_url):
    if not wikipedia_url:
        return None
    try:
        response = requests.get(wikipedia_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        logo_img = soup.select_one("table.infobox img")
        if logo_img:
            return "https:" + logo_img["src"]
        else:
            return None
    except Exception as e:
        print(f"Error fetching logo from Wikipedia: {e}")
        return None


# Check cache and fetch team info
def get_constructor_and_logo(driver_id, year):
    # Check cache in Supabase
    try:
        result = supabase.table("constructors").select("*").eq("driver_id", driver_id).eq("season", year).execute().data
        if result:
            cached_entry = result[0]
            last_updated = datetime.fromisoformat(cached_entry["last_updated"])
            if datetime.now() - last_updated < CACHE_EXPIRY:
                return {
                    "team_name": cached_entry["team_name"],
                    "team_logo": cached_entry["team_logo"],
                }

        # If not cached or expired, fetch fresh data
        constructor = fetch_constructor(driver_id, year)
        logo = fetch_logo_from_wikipedia(constructor["wikipedia_url"])

        # Save to database
        supabase.table("constructors").upsert({
            "driver_id": driver_id,
            "team_name": constructor["name"],
            "team_logo": logo,
            "season": year,
            "last_updated": datetime.now().isoformat(),
        }).execute()

        return {
            "team_name": constructor["name"],
            "team_logo": logo,
        }
    except Exception as e:
        print(f"Error with constructor cache for {driver_id} in {year}: {e}")
        return {"team_name": "Unknown", "team_logo": None}
