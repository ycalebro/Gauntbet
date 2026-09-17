-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Custom Enums
CREATE TYPE game_status AS ENUM ('scheduled', 'in_progress', 'final', 'postponed', 'canceled');
CREATE TYPE bet_market AS ENUM ('spread', 'moneyline', 'over_under');
CREATE TYPE bet_status AS ENUM ('pending', 'matched', 'won', 'lost', 'push', 'void', 'cashed_out');
CREATE TYPE challenge_type AS ENUM ('1v1', 'group');

-- USERS
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    handle VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    avatar_url TEXT,
    h2h_wins INT DEFAULT 0,
    h2h_losses INT DEFAULT 0,
    h2h_draws INT DEFAULT 0,
    early_cashouts INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- GAMES
CREATE TABLE games (
    game_id VARCHAR(100) PRIMARY KEY,
    sport_key VARCHAR(50) NOT NULL,
    home_team VARCHAR(100) NOT NULL,
    away_team VARCHAR(100) NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    status game_status DEFAULT 'scheduled',
    home_score INT DEFAULT 0,
    away_score INT DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- USER BETS
CREATE TABLE user_bets (
    bet_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,
    game_id VARCHAR(100) REFERENCES games(game_id) ON DELETE CASCADE,
    market bet_market NOT NULL,
    selected_team VARCHAR(100) NOT NULL,
    line NUMERIC(4,1),
    odds INT NOT NULL,
    units NUMERIC(6,2) NOT NULL,
    status bet_status DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- MATCHUPS
CREATE TABLE matchups (
    matchup_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type challenge_type NOT NULL,
    creator_id UUID REFERENCES users(user_id),
    title VARCHAR(100),
    status bet_status DEFAULT 'pending',
    winner_id UUID REFERENCES users(user_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- MATCHUP ENTRIES
CREATE TABLE matchup_entries (
    entry_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    matchup_id UUID REFERENCES matchups(matchup_id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,
    bet_id UUID REFERENCES user_bets(bet_id) ON DELETE CASCADE,
    is_winner BOOLEAN DEFAULT NULL,
    UNIQUE(matchup_id, user_id)
);

CREATE OR REPLACE FUNCTION settle_game_bets(p_game_id VARCHAR)
RETURNS VOID AS $$
DECLARE
    r_game RECORD;
    r_bet RECORD;
    v_home_diff INT;
BEGIN
    -- Fetch target game
    SELECT * INTO r_game FROM games WHERE game_id = p_game_id AND status = 'final';
    IF NOT FOUND THEN RETURN; END IF;

    v_home_diff := r_game.home_score - r_game.away_score;

    -- Settle Individual Bets
    FOR r_bet IN SELECT * FROM user_bets WHERE game_id = p_game_id AND status = 'pending' LOOP
        IF r_bet.market = 'spread' THEN
            -- Check if selected team was home or away
            IF r_bet.selected_team = r_game.home_team THEN
                IF (v_home_diff + r_bet.line) > 0 THEN
                    UPDATE user_bets SET status = 'won' WHERE bet_id = r_bet.bet_id;
                ELSIF (v_home_diff + r_bet.line) < 0 THEN
                    UPDATE user_bets SET status = 'lost' WHERE bet_id = r_bet.bet_id;
                ELSE
                    UPDATE user_bets SET status = 'push' WHERE bet_id = r_bet.bet_id;
                END IF;
            ELSE -- Away Team
                IF ((-v_home_diff) + r_bet.line) > 0 THEN
                    UPDATE user_bets SET status = 'won' WHERE bet_id = r_bet.bet_id;
                ELSIF ((-v_home_diff) + r_bet.line) < 0 THEN
                    UPDATE user_bets SET status = 'lost' WHERE bet_id = r_bet.bet_id;
                ELSE
                    UPDATE user_bets SET status = 'push' WHERE bet_id = r_bet.bet_id;
                END IF;
            END IF;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;
