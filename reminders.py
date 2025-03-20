import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from supabase.client import create_client, Client
from dotenv import load_dotenv
import os
import requests
import pyautogui
import time
import pywhatkit as kit
import argparse


# Load environment variables from a custom file (e.g., `config.env`)
load_dotenv("reminders.env")  # Change "email.env" to your actual file name

# Supabase configuration
SUPABASE_URL = os.getenv("supabaseURL2025")
SUPABASE_KEY = os.getenv("supabaseKEY2025")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)  # Initialize Supabase client

# Email configuration
SMTP_SERVER = "smtp.gmail.com"  # Change for your email provider
SMTP_PORT = 587
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")  # Change to your email address
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")  # Change to your email password

# Fixed recipient
RECIPIENT_EMAIL = os.getenv("EMAIL_RECIPIENT_ADDRESS")
PHONE_NUMBER = os.getenv("PHONE")  # Replace with the phone number for WhatsApp
WHATSAPP_GROUP_ID = "DsL6YuZeu9wHtiLGY6WTBN"  # Replace with your WhatsApp group name

# Constants
YEAR = 2025  # or set dynamically based on the current year

def fetch_race_schedule():
    """Fetch the race schedule from an API."""
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

def get_current_race_round():
    """Fetch the current race round based on today's date."""
    races = fetch_race_schedule()
    today = datetime.today().date()
    current_round = None

    # Find the current race round based on today's date
    for race in races:
        race_date = datetime.strptime(race["date"], "%Y-%m-%d").date()
        if race_date >= today:
            current_round = race["round"]
            break
    return current_round

def get_users_without_selection(race_round):
    """Fetch users who have not made a driver selection for the given race round."""
    selected_users = (
        supabase.table("selections")
        .select("username")
        .eq("race_round", race_round)
        .is_("selected_driver", None)
        .execute()
        .data
    )
    if selected_users is None:
        print("No users found.")
        return []  # Return an empty list if no users are found
    usernames = [user['username'] for user in selected_users]
    return usernames

def send_email(recipient_email, missing_users, race_round):
    """Send an email with the list of users who haven't made a selection."""
    subject = f"Race Round {race_round} - Missing Driver Selections"
    
    if missing_users:
        body = (
            f"Hello,\n\n"
            f"The following users have NOT made a driver selection for race round {race_round}:\n\n"
            f"{', '.join(missing_users)}\n\n"
            f"Please remind them to submit their selections before the deadline.\n\nThanks!"
        )
    else:
        body = f"Hello,\n\nAll users have made their selections for race round {race_round}. No action needed!\n\nThanks!"

    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, recipient_email, msg.as_string())
        print(f"Email sent to {recipient_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def send_whatsapp_message_immediately(phone_number, message):
    """Send a WhatsApp message immediately to a phone number."""
    try:
        kit.sendwhatmsg_instantly(phone_number, message)
        print(f"WhatsApp message drafted to {phone_number}")
        
        # Wait for a few seconds to ensure the message box is ready
        time.sleep(5)  # You can adjust this delay depending on your internet speed

        # Simulate pressing the "Enter" key to send the message
        pyautogui.press('enter')
        print(f"WhatsApp message sent to {phone_number}")
        
        # Wait a little bit to ensure the message is sent
        time.sleep(2)  # Adjust this if needed
        
        # Simulate pressing Ctrl+W to close the browser tab
        pyautogui.hotkey('ctrl', 'w')
        print("Closed the WhatsApp web tab")
    except Exception as e:
        print(f"Failed to send WhatsApp message: {e}")


def send_whatsapp_group_message(group_id, message):
    """Send a WhatsApp message to a group immediately."""
    try:
        kit.sendwhatmsg_to_group_instantly(group_id, message)
        print(f"WhatsApp message drafted to group {group_id}")
        
        # Wait for a few seconds to ensure the message box is ready
        time.sleep(5)  # You can adjust this delay depending on your internet speed

        # Simulate pressing the "Enter" key to send the message
        pyautogui.press('enter')
        print(f"WhatsApp message sent to group {group_id}")
        
        # Wait a little bit to ensure the message is sent
        time.sleep(2)  # Adjust this if needed
        
        # Simulate pressing Ctrl+W to close the browser tab
        pyautogui.hotkey('ctrl', 'w')
        print("Closed the WhatsApp web tab")
    except Exception as e:
        print(f"Failed to send WhatsApp message to group: {e}")

def parse_arguments():
    """Parse command-line arguments for phone number, email, and WhatsApp group ID."""
    parser = argparse.ArgumentParser(description="Send race reminders via email and WhatsApp.")
    parser.add_argument("--phone", type=str, required=False, help="Phone number for WhatsApp (include country code, e.g., +14151234567)")
    parser.add_argument("--email", type=str, required=False, help="Recipient email address")
    parser.add_argument("--group", type=str, required=False, help="WhatsApp group ID")
    return parser.parse_args()

def main():
    args = parse_arguments()
    
    race_round = get_current_race_round()  # Dynamically fetch the race round
    if not race_round:
        print("Unable to determine the current race round.")
        return
    
    users_to_notify = get_users_without_selection(race_round)
    print(f"Users to notify: {users_to_notify}")

    if not users_to_notify:
        print(f"All users have made their selections for race round {race_round}. No action needed!")
        return
    
    # Prepare message for WhatsApp
    message = f"The following users have NOT made a driver selection for race round {race_round}: {', '.join(users_to_notify)}. Please remind them!"
    
    # Send email if email argument is provided
    if args.email:
        send_email(args.email, users_to_notify, race_round)

    # Send WhatsApp message to an individual if phone argument is provided
    if args.phone:
        send_whatsapp_message_immediately(args.phone, message)

    # Send WhatsApp message to a group if group argument is provided
    if args.group:
        send_whatsapp_group_message(args.group, message)

if __name__ == "__main__":
    main()
