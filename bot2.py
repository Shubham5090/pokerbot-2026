import random
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot

class Player(BaseBot):
    def __init__(self) -> None:
        self.rank_values = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
                            '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}

    def evaluate_texture(self, board):
        """Classifies the board as 'dry', 'semi-wet', or 'wet'."""
        if not board or len(board) < 3: return 'dry'
       
        suits = [card[1] for card in board]
        ranks = sorted([self.rank_values[card[0]] for card in board])
       
        suit_counts = {s: suits.count(s) for s in set(suits)}
        max_suit = max(suit_counts.values()) if suit_counts else 0
       
        # Check connectivity (gaps between ranks)
        gaps = sum(ranks[i+1] - ranks[i] for i in range(len(ranks)-1))
       
        if max_suit >= 3 or (gaps <= 3 and len(ranks) >= 3):
            return 'wet'
        if max_suit == 2 or gaps <= 5:
            return 'semi-wet'
        return 'dry'

    def detect_draw(self, my_cards, board):
        """Basic heuristic to detect if we have a flush or straight draw."""
        if not board: return False
        all_cards = my_cards + board
        suits = [c[1] for c in all_cards]
        suit_counts = {s: suits.count(s) for s in set(suits)}
        if any(count == 4 for count in suit_counts.values()):
            return True # Flush draw
        return False # (Simplified straight draw detection can be added here)

    def is_made_hand(self, my_cards, board):
        """Checks for Top Pair or better."""
        if not board: return my_cards[0][0] == my_cards[1][0] and self.rank_values[my_cards[0][0]] >= 10
        board_ranks = [self.rank_values[c[0]] for c in board]
        my_ranks = [self.rank_values[c[0]] for c in my_cards]
       
        # Pocket overpair or paired with highest board card
        if my_ranks[0] == my_ranks[1] and my_ranks[0] > max(board_ranks): return True
        if max(my_ranks) == max(board_ranks) and max(my_ranks) in my_ranks: return True
        return False

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        pass

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        pass

    def get_move(self, game_info: GameInfo, current_state: PokerState) -> ActionFold | ActionCall | ActionCheck | ActionRaise | ActionBid:
        my_cards = current_state.my_hand
        board = getattr(current_state, 'board', [])
        street = current_state.street
        pot = getattr(current_state, 'pot', 40) # Fallback if not injected

        texture = self.evaluate_texture(board)
        has_draw = self.detect_draw(my_cards, board)
        made_hand = self.is_made_hand(my_cards, board)

        # --------------------------------------------------------
        # 1. THE SNEAK (Auction Phase)
        # Value = Uncertainty. We bid high on draws/wet boards.
        # --------------------------------------------------------
        if street == 'auction':
            if has_draw or (texture == 'wet' and not made_hand):
                # High uncertainty, massive fold-equity potential = High Bid
                bid_amt = int(pot * 0.20)
            elif texture == 'semi-wet' and not made_hand:
                bid_amt = int(pot * 0.10)
            elif made_hand:
                # We have showdown equity. Info is nice but not critical = Low Bid
                bid_amt = int(pot * 0.05)
            else:
                # Pure trash on dry board = 0
                bid_amt = 0
           
            return ActionBid(min(bid_amt, current_state.my_chips))

        # --------------------------------------------------------
        # 2. POST-AUCTION BAYESIAN UPDATES & BLUFFING
        # --------------------------------------------------------
        bluff_multiplier = 1.0
        if current_state.opp_revealed_cards:
            opp_card = current_state.opp_revealed_cards[0]
            opp_val = self.rank_values[opp_card[0]]
           
            # If they revealed a weak card (< 9) that doesn't hit the board
            board_vals = [self.rank_values[c[0]] for c in board] if board else []
            if opp_val < 9 and opp_val not in board_vals:
                bluff_multiplier = 2.0 # Green light to aggressively bluff/c-bet
            elif opp_val >= 10 or opp_val in board_vals:
                bluff_multiplier = 0.0 # Red light, shut down bluffs

        # --------------------------------------------------------
        # 3. DYNAMIC BETTING ENGINE
        # --------------------------------------------------------
        can_raise = current_state.can_act(ActionRaise)
        min_raise, max_raise = current_state.raise_bounds if can_raise else (0, 0)
        cost = current_state.cost_to_call

        # Pre-flop (Simplified for brevity, keeping it tight)
        if not board:
            my_ranks = sorted([self.rank_values[c[0]] for c in my_cards], reverse=True)
            if my_ranks[0] >= 10 and my_ranks[1] >= 10 or my_ranks[0] == my_ranks[1]:
                if can_raise: return ActionRaise(min(max_raise, max(min_raise, int(pot * 1.5))))
                return ActionCall()
            if cost < 50: return ActionCall()
            return ActionFold() if not current_state.can_act(ActionCheck) else ActionCheck()

        # Post-Flop: Made Hands (Value Betting)
        if made_hand:
            # Randomize check to protect checking range (15% trap rate)
            if random.random() < 0.15 and current_state.can_act(ActionCheck):
                return ActionCheck()
           
            if can_raise:
                target_raise = int(pot * 0.75) # 3/4 pot value bet
                return ActionRaise(min(max_raise, max(min_raise, target_raise)))
            return ActionCall()

        # Post-Flop: Draws (Semi-Bluffing)
        if has_draw:
            # Semi-bluff using fold equity derived from the revealed card
            if can_raise and random.random() < (0.6 * bluff_multiplier):
                target_raise = int(pot * 0.8) # Aggressive semi-bluff
                return ActionRaise(min(max_raise, max(min_raise, target_raise)))
            if cost < (pot * 0.35): # Pot odds call
                return ActionCall()
            return ActionFold() if not current_state.can_act(ActionCheck) else ActionCheck()

        # Post-Flop: Air (C-Betting & Pure Bluffs)
        if not made_hand and not has_draw:
            if can_raise and random.random() < (0.3 * bluff_multiplier):
                # C-bet / Pure Bluff sizing
                target_raise = int(pot * 0.5)
                return ActionRaise(min(max_raise, max(min_raise, target_raise)))
           
            if current_state.can_act(ActionCheck): return ActionCheck()
            return ActionFold()

if __name__ == '__main__':
    run_bot(Player(), parse_args())