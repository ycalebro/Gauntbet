import os
from dotenv import load_dotenv
from supabase import create_client, Client
from odds_fetcher import fetch_upcoming_games, fetch_live_scores

# Load environment variables from local .env file
load_dotenv()

# Initialize the Supabase Client with target URL and secret API key
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)


def sync_upcoming_slates(sports=["americanfootball_nfl", "basketball_nba"]):
    """
    Fetches incoming fixtures for specific sports leagues and upserts
    them into the Supabase 'games' table to keep game states current
    """
    for sport in sports:
        # Fetch formatted game dicts from The Odds API module
        games = fetch_upcoming_games(sport)

        if games:
            # Perform an upsert (insert new rows, or update if 'game_id' already exists)
            response = supabase.table("games").upsert(games, on_conflict="game_id").execute()
            print(f"Synced {len(games)} games for {sport}.")


def sync_scores_and_settle(sports=["americanfootball_nfl"]):
    """
    Updates scores/statuses and triggers settlement procedures for completed games.
    """
    for sport in sports:
        # Retrieve live and recently finished score payloads
        scores_data = fetch_live_scores(sport)

        for game in scores_data:
            # Only process games that have officially completed
            if game.get("completed"):
                # Extract final scores and parse into convenient {team_name: score_int} dicts
                scores = {s["name"]: int(s["score"]) for s in game.get("scores", []) if "score" in s}
                home_team = game["home_team"]
                away_team = game["away_team"]

                # Ensure scores exist for both participating teams
                if home_team in scores and away_team in scores:
                    # Update game row in db
                    update_payload = {
                        "status": "final",
                        "home_score": scores[home_team],
                        "away_score": scores[away_team]
                    }

                    # Update db row for the completed game
                    supabase.table("games").update(update_payload).eq("game_id", game["id"]).execute()

                    # Call the SQL settlement function created in Phase 1 to settle bets
                    supabase.rpc("settle_game_bets", {"p_game_id": game["id"]}).execute()
                    print(f"Game {game['id']} settled automatically.")


# ------------------------------------------------------------------------------------
# Script Execution Entry Point
# ------------------------------------------------------------------------------------
if __name__ == "__main__":
    print("--- Starting Phase 2 Data Ingestion ---")
    # Sync active and upcoming game slates
    sync_upcoming_slates()

    # Check for completed games and trigger bet settlements
    sync_scores_and_settle()
