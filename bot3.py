import random
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot

class Player(BaseBot):
    def __init__(self) -> None:
        self.rank_values = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
                            '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        self.all_ranks = list(self.rank_values.keys())
        self.all_suits = ['s', 'h', 'd', 'c']
        self.full_deck = [r+s for r in self.all_ranks for s in self.all_suits]
       
        # --- STATISTICAL TRACKING ---
        self.opp_fold_ema = 0.5  
        self.last_action_was_aggressive = False

    def evaluate_texture(self, board):
        if not board or len(board) < 3: return 'dry'
        suits = [card[1] for card in board]
        ranks = sorted([self.rank_values[card[0]] for card in board])
        max_suit = max({s: suits.count(s) for s in set(suits)}.values()) if suits else 0
        gaps = sum(ranks[i+1] - ranks[i] for i in range(len(ranks)-1))
       
        if max_suit >= 3 or (gaps <= 3 and len(ranks) >= 3): return 'wet'
        if max_suit == 2 or gaps <= 5: return 'semi-wet'
        return 'dry'

    def detect_draw(self, cards, board):
        if not board: return False
        all_cards = cards + board
        suits = [c[1] for c in all_cards]
        if any(suits.count(s) >= 4 for s in set(suits)): return True
        return False

    def is_made_hand(self, cards, board):
        """Strict check for Top Pair or better"""
        if not board: return cards[0][0] == cards[1][0] and self.rank_values[cards[0][0]] >= 10
        board_ranks = [self.rank_values[c[0]] for c in board]
        my_ranks = [self.rank_values[c[0]] for c in cards]
       
        # Pocket pair higher than the board
        if my_ranks[0] == my_ranks[1] and my_ranks[0] > max(board_ranks): return True
        # Paired with the highest card on the board
        if max(my_ranks) == max(board_ranks) and max(my_ranks) in my_ranks: return True
        return False

    def evaluate_opponent_range(self, opp_revealed_card, board, my_cards):
        """
        Calculates EXACTLY what percentage of the opponent's remaining 46 possible
        hands are dangerous (Made Hands or Strong Draws).
        """
        if not board or not opp_revealed_card: return 0.5
       
        dead_cards = set(my_cards + board + [opp_revealed_card[0]])
        possible_other_cards = [c for c in self.full_deck if c not in dead_cards]
       
        dangerous_combos = 0
        for unseen_card in possible_other_cards:
            test_hand = [opp_revealed_card[0], unseen_card]
            if self.is_made_hand(test_hand, board) or self.detect_draw(test_hand, board):
                dangerous_combos += 1
               
        # Return the probability that their range hit the board
        return dangerous_combos / len(possible_other_cards)

    def estimate_equity(self, my_cards, board):
        """Basic self-equity heuristic"""
        if not board:
            my_ranks = sorted([self.rank_values[c[0]] for c in my_cards], reverse=True)
            eq = (my_ranks[0] * 2 + my_ranks[1]) / 100.0
            if my_ranks[0] == my_ranks[1]: eq += 0.20
            if my_cards[0][1] == my_cards[1][1]: eq += 0.05
            return min(0.85, eq)

        if self.is_made_hand(my_cards, board) and self.detect_draw(my_cards, board): return 0.85
        if self.is_made_hand(my_cards, board): return 0.65
        if self.detect_draw(my_cards, board): return 0.35
        return 0.10

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        self.last_action_was_aggressive = False

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        if self.last_action_was_aggressive:
            if current_state.payoff > 0 and current_state.street != 'showdown':
                self.opp_fold_ema = 0.8 * self.opp_fold_ema + 0.2 * 1.0
            elif current_state.street == 'showdown':
                self.opp_fold_ema = 0.8 * self.opp_fold_ema + 0.2 * 0.0

    def get_move(self, game_info: GameInfo, current_state: PokerState) -> ActionFold | ActionCall | ActionCheck | ActionRaise | ActionBid:
        my_cards = current_state.my_hand
        board = getattr(current_state, 'board', [])
        street = current_state.street
        pot = getattr(current_state, 'pot', 40)
        cost = current_state.cost_to_call
       
        is_bb = current_state.is_bb
        in_pos_postflop = not is_bb

        texture = self.evaluate_texture(board)
        has_draw = self.detect_draw(my_cards, board)
        made_hand = self.is_made_hand(my_cards, board)
        equity = self.estimate_equity(my_cards, board)
        pot_odds = cost / (pot + cost) if (pot + cost) > 0 else 0

        can_raise = current_state.can_act(ActionRaise)
        min_raise, max_raise = current_state.raise_bounds if can_raise else (0, 0)

        def execute_raise(amount):
            self.last_action_was_aggressive = True
            return ActionRaise(min(max_raise, max(min_raise, amount)))

        # --------------------------------------------------------
        # 1. THE SNEAK (Auction Phase - Range Based)
        # --------------------------------------------------------
        if street == 'auction':
            evi_fraction = 0.0
            if has_draw: evi_fraction = 0.15
            elif not made_hand and texture == 'dry': evi_fraction = 0.08
            elif made_hand and texture == 'wet': evi_fraction = 0.05
            elif made_hand and texture == 'dry': evi_fraction = 0.01
           
            return ActionBid(min(int(pot * evi_fraction), current_state.my_chips))

        # --------------------------------------------------------
        # 2. EXACT RANGE EVALUATION (The Final Upgrade)
        # --------------------------------------------------------
        opp_danger_prob = 0.5 # Default unknown
        if current_state.opp_revealed_cards:
            opp_danger_prob = self.evaluate_opponent_range(current_state.opp_revealed_cards, board, my_cards)

        # --------------------------------------------------------
        # 3. RANGE-DRIVEN DECISION ENGINE
        # --------------------------------------------------------
       
        # Pre-flop
        if not board:
            if equity > 0.60:
                if can_raise: return execute_raise(int(pot * 1.5))
                return ActionCall()
            if equity >= pot_odds: return ActionCall()
            return ActionFold() if not current_state.can_act(ActionCheck) else ActionCheck()

        # Post-Flop: Value Betting
        if made_hand:
            # If their range is highly dangerous (>60% strong hands), transition to pot control
            if opp_danger_prob > 0.60:
                if cost < pot * 0.5: return ActionCall()
                return ActionCheck() if current_state.can_act(ActionCheck) else ActionFold()

            if can_raise:
                sizing = 0.5 if self.opp_fold_ema > 0.6 else 0.8
                return execute_raise(int(pot * sizing))
            return ActionCall() if equity >= pot_odds else (ActionCheck() if current_state.can_act(ActionCheck) else ActionFold())

        # Post-Flop: Semi-Bluffing Draws
        if has_draw:
            # Only semi-bluff if their range is mathematically weak (<40% strong hands)
            if can_raise and opp_danger_prob < 0.40 and random.random() < 0.8:
                return execute_raise(int(pot * 0.75))
           
            if equity >= pot_odds: return ActionCall()
            return ActionFold() if not current_state.can_act(ActionCheck) else ActionCheck()

        # Post-Flop: Pure Air & C-Betting
        if not made_hand and not has_draw:
            # Mathematically perfect bluffing: Target them when their range completely misses the board
            if can_raise and opp_danger_prob < 0.25 and self.opp_fold_ema > 0.5:
                return execute_raise(int(pot * 0.6))
                   
            if current_state.can_act(ActionCheck): return ActionCheck()
            return ActionFold()

if __name__ == '__main__':
    run_bot(Player(), parse_args())
