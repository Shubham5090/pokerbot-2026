import random
import eval7
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot

# We define the ranks and suits to reconstruct a deck efficiently
RANKS = "23456789TJQKA"
SUITS = "cdhs"
ALL_CARDS = [r + s for r in RANKS for s in SUITS]

def calc_equity(my_cards_str, board_cards_str, opp_revealed_card=None, iters=300):
    """
    Calculate the equity of our hand using Monte Carlo simulations with eval7.
    """
    # 1. Parse our cards and board
    my_hand = [eval7.Card(c) for c in my_cards_str]
    board = [eval7.Card(c) for c in board_cards_str]
    
    # 2. Build the remaining deck
    known_cards = my_hand + board
    if opp_revealed_card:
        known_cards.append(eval7.Card(opp_revealed_card))

    # Fast deck construction by skipping known cards
    known_set = set(known_cards)
    deck = [eval7.Card(c) for c in ALL_CARDS if eval7.Card(c) not in known_set]
    
    wins = 0
    ties = 0

    # 3. MC Loop
    for _ in range(iters):
        # We need to draw:
        # - remaining board cards to make it 5
        # - opponent hole cards (2 if none revealed, 1 if one revealed)
        cards_needed = (5 - len(board)) + (1 if opp_revealed_card else 2)
        
        # sample without replacement
        drawn = random.sample(deck, cards_needed)
        
        sim_board = board + drawn[:5 - len(board)]
        
        if opp_revealed_card:
            sim_opp = [eval7.Card(opp_revealed_card), drawn[-1]]
        else:
            sim_opp = drawn[5 - len(board):]

        my_score = eval7.evaluate(my_hand + sim_board)
        opp_score = eval7.evaluate(sim_opp + sim_board)

        if my_score > opp_score:
            wins += 1
        elif my_score == opp_score:
            ties += 1

    return (wins + 0.5 * ties) / iters

class Player(BaseBot):
    def __init__(self) -> None:
        self.total_rounds = 1000
        pass

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        pass

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        pass

    def get_move(self, game_info: GameInfo, current_state: PokerState) -> ActionFold | ActionCall | ActionCheck | ActionRaise | ActionBid:
        # Parse inputs
        street = current_state.street
        my_chips = current_state.my_chips
        cost_to_call = current_state.cost_to_call
        pot = current_state.pot

        opp_revealed = current_state.opp_revealed_cards[0] if current_state.opp_revealed_cards else None

        # --- Auction Logic (Pre-Flop) ---
        if street == 'auction':
            # Preflop equity
            equity = calc_equity(current_state.my_hand, [], opp_revealed, iters=300)
            
            # If we have a strong hand, bid to win the auction and gain info.
            if equity > 0.55:
                # E.g. Equity 0.65 -> bid ~ 6% of our stack
                bid_fraction = max(0.0, equity - 0.5) * 0.6
                bid_amt = int(my_chips * bid_fraction)
            else:
                bid_amt = 0
                
            return ActionBid(min(bid_amt, my_chips))

        # --- Flop/Turn/River/Pre-Flop Action Logic ---
        
        # Determine simulation iterations based on street and time. 
        # For simplicity, 200 is fast enough with eval7
        equity = calc_equity(current_state.my_hand, current_state.board, opp_revealed, iters=200)

        pot_odds = cost_to_call / (pot + cost_to_call) if (pot + cost_to_call) > 0 else 0

        # Action: Raise
        if current_state.can_act(ActionRaise) and equity > 0.65:
            min_raise, max_raise = current_state.get_raise_limits()
            # Try to raise around half the pot
            desired_raise = cost_to_call + (pot // 2)
            actual_raise = max(min_raise, min(desired_raise, max_raise))
            return ActionRaise(actual_raise)
            
        # Action: Call or Check (if no cost)
        if current_state.can_act(ActionCheck) and cost_to_call == 0:
            return ActionCheck()
            
        if current_state.can_act(ActionCall) and (equity > 0.40 or equity > pot_odds):
            return ActionCall()

        # Action: Fold (default)
        if current_state.can_act(ActionFold):
            return ActionFold()

        return ActionCheck()

if __name__ == '__main__':
    run_bot(Player(), parse_args())