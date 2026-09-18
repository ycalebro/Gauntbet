import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Retrieve API key for The Odds API from env
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

# Base URL endpoint for The Odds API v4 sports service
BASE_URL = "https://api.the-odds-api.com/v4/sports"


def fetch_upcoming_games(sport_key="americanfootball_nfl"):
    """Fetches upcoming fixtures and game metadata for a given sport."""

    # Construct endpoint URL for fetching active events
    url = f"{BASE_URL}/{sport_key}/events"

    # Query parameters including the auth key
    params = {
        "apiKey": ODDS_API_KEY,
    }

    # Send GET request to fetch events
    response = requests.get(url, params=params)

    # Handle API request failure
    if response.status_code != 200:
        print(f"Error fetching data: {response.status_code} - {response.text}")
        return []

    events = response.json()
    formatted_games = []

    # Map external API event fields to match Supabase 'games' table schema
    for event in events:
        formatted_games.append({
            "game_id": event["id"],     # Unique event identifier
            "sport_key": sport_key,     # League/sport category (i.e. 'americanfootball_nfl')
            "home_team": event["home_team"],        # Designated home team name
            "away_team": event["away_team"],        # Designated away team name
            "start_time": event["commence_time"],   # ISO 8601 UTC timestamp of game start
            "status": "scheduled"                   # Initial status for upcoming games
        })

    return formatted_games


def fetch_live_scores(sport_key="americanfootball_nfl"):
    """Fetches live and recently completed game scores to feed the settlement engine."""

    # Construct endpoint URL for live/recent scores
    url = f"{BASE_URL}/{sport_key}/scores"

    # Query params requesting games from the past 1 day
    params = {
        "apiKey": ODDS_API_KEY,
        "daysFrom": 1   # Lookback window in days for recent/completed games
    }

    # Send GET request to fetch scores payload
    response = requests.get(url, params=params)

    # Handle API request failure
    if response.status_code != 200:
        print(f"Error fetching scores: {response.status_code}")
        return []

    # Return raw list of game objects containing score arrays and completion status
    return response.json()
