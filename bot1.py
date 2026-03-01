from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot

import random
import itertools

class Player(BaseBot):
    def __init__(self) -> None:
        self.RANKS = "23456789TJQKA"
        self.SUITS = "shdc"
        self.my_raise_count = 0

    # -------------------------
    # Fast Hand Evaluator
    # -------------------------
    def hand_rank(self, cards):
        ranks = sorted([self.RANKS.index(c[0]) for c in cards], reverse=True)
        suits = [c[1] for c in cards]

        counts = {r: ranks.count(r) for r in set(ranks)}
        count_values = sorted(counts.values(), reverse=True)

        is_flush = len(set(suits)) == 1
        is_straight = len(set(ranks)) == 5 and (max(ranks) - min(ranks) == 4)
       
        # Special case: A-2-3-4-5 straight
        if set(ranks) == {12, 0, 1, 2, 3}:
            is_straight = True
            ranks = [3, 2, 1, 0, -1] # Treat Ace as low

        if is_straight and is_flush: return (8, max(ranks))
        if 4 in count_values: return (7, ranks)
        if 3 in count_values and 2 in count_values: return (6, ranks)
        if is_flush: return (5, ranks)
        if is_straight: return (4, max(ranks))
        if 3 in count_values: return (3, ranks)
        if count_values.count(2) == 2: return (2, ranks)
        if 2 in count_values: return (1, ranks)
        return (0, ranks)

    def best_hand(self, seven_cards):
        best = None
        # Evaluate all 5-card combinations to find the highest standard poker hand
        for combo in itertools.combinations(seven_cards, 5):
            rank = self.hand_rank(combo)
            if best is None or rank > best:
                best = rank
        return best

    # -------------------------
    # Monte Carlo Win Predictor (Solves TLE)
    # -------------------------
    def monte_carlo_win_pct(self, my_hand, board, opp_known_card=None, simulations=200):
        """
        Runs fast random sampling instead of exhaustive generation to avoid TLE.
        """
        deck = [r+s for r in self.RANKS for s in self.SUITS]
        known = my_hand + board
        if opp_known_card:
            known.append(opp_known_card)
           
        available_deck = [c for c in deck if c not in known]
        wins = ties = 0
       
        cards_needed = 5 - len(board)
        opp_cards_needed = 1 if opp_known_card else 2

        for _ in range(simulations):
            # Randomly draw remaining cards
            sampled = random.sample(available_deck, cards_needed + opp_cards_needed)
            opp_hole = sampled[:opp_cards_needed]
            if opp_known_card:
                opp_hole.append(opp_known_card)
               
            future_board = sampled[opp_cards_needed:]
            full_board = board + future_board
           
            my_best = self.best_hand(my_hand + full_board)
            opp_best = self.best_hand(opp_hole + full_board)
           
            if my_best > opp_best:
                wins += 1
            elif my_best == opp_best:
                ties += 1
               
        return 100 * (wins + 0.5 * ties) / simulations

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        self.my_raise_count = 0 # Reset raise counter each round

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        pass

    # -------------------------
    # Main Decision Engine
    # -------------------------
    def get_move(self, game_info: GameInfo, current_state: PokerState) -> ActionFold | ActionCall | ActionCheck | ActionRaise | ActionBid:
       
        my_cards = current_state.my_hand
        board = getattr(current_state, 'board', [])
        street = current_state.street

        # ==========================================================
        # AUCTION PHASE
        # ==========================================================
        if street == 'auction':
            win_pct = self.monte_carlo_win_pct(my_cards, board, simulations=150)
            chips = current_state.my_chips
           
            # Sane bidding logic: High uncertainty (40-70%) = High Value of Info
            if 40 <= win_pct <= 70:
                bid_amount = int(0.15 * chips) # Bid 15% to clear up uncertainty
            else:
                bid_amount = int(0.02 * chips) # Bid tiny amount if we are already winning/losing
               
            return ActionBid(min(bid_amount, chips))

        # Determine win percentages for betting
        opp_revealed = current_state.opp_revealed_cards
        if opp_revealed:
            win_pct = self.monte_carlo_win_pct(my_cards, board, opp_known_card=opp_revealed[0], simulations=200)
        else:
            win_pct = self.monte_carlo_win_pct(my_cards, board, simulations=200)

        # Helper function for safe raises
        can_raise = current_state.can_act(ActionRaise)
        min_r, max_r = current_state.raise_bounds if can_raise else (0, 0)
       
        def safe_raise():
            self.my_raise_count += 1
            target_raise = min(2 * min_r, max_r)
            return ActionRaise(max(min_r, target_raise))

        # ==========================================================
        # CASE 1: Opponent has revealed a card
        # ==========================================================
        if opp_revealed:
            # > 60 → Raise (preferably 2x min raise), else call
            if win_pct > 60:
                if self.my_raise_count < 2 and can_raise:
                    return safe_raise()
                if current_state.can_act(ActionCall): return ActionCall()
                if current_state.can_act(ActionCheck): return ActionCheck()

            # 20–60 → Call
            elif 20 <= win_pct <= 60:
                if current_state.can_act(ActionCall): return ActionCall()
                if current_state.can_act(ActionCheck): return ActionCheck()

            # < 20 → Fold
            else:
                if current_state.can_act(ActionCheck): return ActionCheck()
                if current_state.can_act(ActionFold): return ActionFold()

        # ==========================================================
        # CASE 2: No opponent card revealed
        # ==========================================================
        else:
            opponent_raised = current_state.cost_to_call > 0

            # If < 40 and opponent raised → Fold
            if win_pct < 40 and opponent_raised:
                if current_state.can_act(ActionFold): return ActionFold()
                if current_state.can_act(ActionCheck): return ActionCheck()

            # If > 70 → Raise
            if win_pct > 70:
                if self.my_raise_count < 2 and can_raise:
                    return safe_raise()
                if current_state.can_act(ActionCall): return ActionCall()
                if current_state.can_act(ActionCheck): return ActionCheck()

            # Otherwise → Call or Check
            if current_state.can_act(ActionCall): return ActionCall()
            if current_state.can_act(ActionCheck): return ActionCheck()

        # Fallback safety (never return invalid action)
        return ActionFold() if current_state.can_act(ActionFold) else ActionCheck()

if __name__ == '__main__':
    run_bot(Player(), parse_args())

