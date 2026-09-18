from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any
from config import supabase


@dataclass
class UserBet:
    bet_id: str
    user_id: str
    game_id: str
    market: str # spread, ML, over_under
    selected_team: str # team selected by user
    line: Optional[float] # point spread or total line (can be None for ML bets)
    odds: int #American odds (i.e. +110)
    units: float # wager stake/value
    status: str # i.e. 'pending', 'matched', 'cashed_out', 'won'

# -----------------------------------------------------------------------------------------------
# Matchmaking Validation Logic
# -----------------------------------------------------------------------------------------------

def validate_h2h_match(bet_a: UserBet, bet_b: UserBet) -> Tuple[bool, Optional[str]]:
   """
   Validates whether two bets satisfy all reqs to form a fair 1v1 mathup
   """
    
    # Ensure both bets are placed on the same game
    if bet_a.game_id != bet_b.game_id:
        return False, "Bets must be for the same game."
        
    # Prevent competitors from picking the same side
    if bet_a.selected_team == bet_b.selected_team:
        return False, "Competitors cannot bet on the same team."
        
    # Ensure both users are wagering on the same market type
    if bet_a.market != bet_b.market:
        return False, "Competitors must bet on the same market type (e.g., spread vs. spread)."
        
    # Market-specific check; Validate spread line symmetry
    if bet_a.market == 'spread':
        
        # Safely coerce values to floats in case they were parsed as numeric strings
        line_a = float(bet_a.line) if bet_a.line is not None else None
        line_b = float(bet_b.line) if bet_b.line is not None else None
        
        # Check for missing spread lines
        if line_a is None or line_b is None:
            return False, "Spread values are required for spread market."
            
        # verify that spread lines offset exactly to zero (i.e. -3.5 and +3.5)
        if line_a + line_b != 0:
            return False, f"Spreads must offset exactly (e.g., -3.5 vs +3.5). Got {line_a} and {line_b}."

    return True, None

# ---------------------------------------------------------------------------------------------------------
# Matchmaking Creation Logic
# ---------------------------------------------------------------------------------------------------------

def create_1v1_matchup(creator_bet_id: str, challenger_bet_id: str) -> Dict[str, Any]:
    """
    Fetches bet records from Supabase, verifies eligibility, and creates the 1v1 matchup entry in the db
    """

    # Retrieve creator and challenger bet records from the db
    res_a = supabase.table("user_bets").select("*").eq("bet_id", creator_bet_id).single().execute()
    res_b = supabase.table("user_bets").select("*").eq("bet_id", challenger_bet_id).single().execute()
    
    # Ensure both bet records exist
    if not res_a.data or not res_b.data:
        return {"success": False, "error": "One or both bets were not found."}
        
    # Instatiate dataclass models from returned db dicts
    bet_a = UserBet(**res_a.data)
    bet_b = UserBet(**res_b.data)
    
    # Run validation checks on the two bets
    is_valid, reason = validate_h2h_match(bet_a, bet_b)
    if not is_valid:
        return {"success": False, "error": reason}
        
    # Insert new record into the 'matchups' table
    matchup_res = supabase.table("matchups").insert({
        "type": "1v1",
        "creator_id": bet_a.user_id,
        "title": f"{bet_a.selected_team} vs {bet_b.selected_team}",
        "status": "matched"
    }).execute()
    
    # Extract the generated primary key for the new matchup
    matchup_id = matchup_res.data[0]["matchup_id"]
    
    # Map both participants into the 'matchup_entries' join table
    supabase.table("matchup_entries").insert([
        {"matchup_id": matchup_id, "user_id": bet_a.user_id, "bet_id": bet_a.bet_id},
        {"matchup_id": matchup_id, "user_id": bet_b.user_id, "bet_id": bet_b.bet_id}
    ]).execute()

    # Update both original bet statuses from 'pending' to 'matched'
    supabase.table("user_bets").update({"status": "matched"}).in_("bet_id", [bet_a.bet_id, bet_b.bet_id]).execute()

    return {"success": True, "matchup_id": matchup_id, "message": "Matchup successfully created!"}

# ------------------------------------------------------------------------------------------------------------------
# Early cashout penalty handler
# ------------------------------------------------------------------------------------------------------------------
def handle_early_cashout(matchup_id: str, cashed_out_user_id: str) -> Dict[str, Any]:
    """
    Handles early cashouts by canceling the active matchup, updating the user's bet status, and incrementing their penalty count in public.users
    """

    # Void/Cancel the active H2H matchup record
    supabase.table("matchups").update({
        "status": "canceled"
    }).eq("matchup_id", matchup_id).execute()

    # Locate the specific bet ID linked to the user who cashed out
    entry_res = supabase.table("matchup_entries") \
        .select("bet_id") \
        .eq("matchup_id", matchup_id) \
        .eq("user_id", cashed_out_user_id) \
        .single() \
        .execute()

    # Mark the target bet's status as 'cashed_out'
    if entry_res.data:
        target_bet_id = entry_res.data["bet_id"]
        supabase.table("user_bets").update({
            "status": "cashed_out"
        }).eq("bet_id", target_bet_id).execute()

    # Retrieve the offending user's current early cashout count
    user_res = supabase.table("users").select("early_cashouts").eq("user_id", cashed_out_user_id).single().execute()

    current_cashouts = 0
    if user_res.data and user_res.data.get("early_cashouts") is not None:
        current_cashouts = user_res.data["early_cashouts"]

    # Increment and penalize the user with a +1 early cashout flag
    supabase.table("users").update({
        "early_cashouts": current_cashouts + 1
    }).eq("user_id", cashed_out_user_id).execute()

    return {
        "success": True,
        "message": f"Matchup {matchup_id} canceled. User {cashed_out_user_id} penalised (+1 Early Cashout Flag)."
    }
