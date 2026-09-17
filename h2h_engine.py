from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any
from config import supabase


@dataclass
class UserBet:
    bet_id: str
    user_id: str
    game_id: str
    market: str
    selected_team: str
    line: Optional[float]
    odds: int
    units: float
    status: str


def validate_h2h_match(bet_a: UserBet, bet_b: UserBet) -> Tuple[bool, Optional[str]]:
    if bet_a.game_id != bet_b.game_id:
        return False, "Bets must be for the same game."

    if bet_a.selected_team == bet_b.selected_team:
        return False, "Competitors cannot bet on the same team."

    if bet_a.market != bet_b.market:
        return False, "Competitors must bet on the same market type (e.g., spread vs. spread)."

    if bet_a.market == 'spread':
        line_a = float(bet_a.line) if bet_a.line is not None else None
        line_b = float(bet_b.line) if bet_b.line is not None else None

        if line_a is None or line_b is None:
            return False, "Spread values are required for spread market."

        if line_a + line_b != 0:
            return False, f"Spreads must offset exactly (e.g., -3.5 vs +3.5). Got {line_a} and {line_b}."

    return True, None


def create_1v1_matchup(creator_bet_id: str, challenger_bet_id: str) -> Dict[str, Any]:
    res_a = supabase.table("user_bets").select("*").eq("bet_id", creator_bet_id).single().execute()
    res_b = supabase.table("user_bets").select("*").eq("bet_id", challenger_bet_id).single().execute()

    if not res_a.data or not res_b.data:
        return {"success": False, "error": "One or both bets were not found."}

    bet_a = UserBet(**res_a.data)
    bet_b = UserBet(**res_b.data)

    is_valid, reason = validate_h2h_match(bet_a, bet_b)
    if not is_valid:
        return {"success": False, "error": reason}

    matchup_res = supabase.table("matchups").insert({
        "type": "1v1",
        "creator_id": bet_a.user_id,
        "title": f"{bet_a.selected_team} vs {bet_b.selected_team}",
        "status": "matched"
    }).execute()

    matchup_id = matchup_res.data[0]["matchup_id"]

    supabase.table("matchup_entries").insert([
        {"matchup_id": matchup_id, "user_id": bet_a.user_id, "bet_id": bet_a.bet_id},
        {"matchup_id": matchup_id, "user_id": bet_b.user_id, "bet_id": bet_b.bet_id}
    ]).execute()

    supabase.table("user_bets").update({"status": "matched"}).in_("bet_id", [bet_a.bet_id, bet_b.bet_id]).execute()

    return {"success": True, "matchup_id": matchup_id, "message": "Matchup successfully created!"}


def handle_early_cashout(matchup_id: str, cashed_out_user_id: str) -> Dict[str, Any]:
    supabase.table("matchups").update({
        "status": "canceled"
    }).eq("matchup_id", matchup_id).execute()

    entry_res = supabase.table("matchup_entries") \
        .select("bet_id") \
        .eq("matchup_id", matchup_id) \
        .eq("user_id", cashed_out_user_id) \
        .single() \
        .execute()

    if entry_res.data:
        target_bet_id = entry_res.data["bet_id"]
        supabase.table("user_bets").update({
            "status": "cashed_out"
        }).eq("bet_id", target_bet_id).execute()

    user_res = supabase.table("users").select("early_cashouts").eq("user_id", cashed_out_user_id).single().execute()

    current_cashouts = 0
    if user_res.data and user_res.data.get("early_cashouts") is not None:
        current_cashouts = user_res.data["early_cashouts"]

    supabase.table("users").update({
        "early_cashouts": current_cashouts + 1
    }).eq("user_id", cashed_out_user_id).execute()

    return {
        "success": True,
        "message": f"Matchup {matchup_id} canceled. User {cashed_out_user_id} penalised (+1 Early Cashout Flag)."
    }
