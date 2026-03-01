import random
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot


class Player(BaseBot):

    def __init__(self):
        self.rank_values = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
                            '8': 8, '9': 9, 'T': 10, 'J': 11,
                            'Q': 12, 'K': 13, 'A': 14}

    # -------------------------------------------------------
    # BOARD TEXTURE
    # -------------------------------------------------------

    def evaluate_texture(self, board):
        if len(board) < 3:
            return "dry"

        suits = [c[1] for c in board]
        ranks = sorted([self.rank_values[c[0]] for c in board])

        suit_count = max(suits.count(s) for s in suits)
        gaps = sum(ranks[i+1] - ranks[i] for i in range(len(ranks)-1))

        if suit_count >= 3 or gaps <= 3:
            return "wet"
        if suit_count == 2 or gaps <= 5:
            return "semi"
        return "dry"

    # -------------------------------------------------------
    # MADE HAND CHECK
    # -------------------------------------------------------

    def classify_hand(self, my_cards, board):

        if not board:
            r1 = self.rank_values[my_cards[0][0]]
            r2 = self.rank_values[my_cards[1][0]]
            if r1 == r2:
                return "pair"
            if r1 >= 11 and r2 >= 11:
                return "strong_high"
            return "weak"

        board_vals = [self.rank_values[c[0]] for c in board]
        my_vals = [self.rank_values[c[0]] for c in my_cards]

        # Overpair
        if my_vals[0] == my_vals[1] and my_vals[0] > max(board_vals):
            return "overpair"

        # Top pair
        if max(my_vals) == max(board_vals):
            return "top_pair"

        # Mid pair
        if any(v in board_vals for v in my_vals):
            return "mid_pair"

        return "air"

    # -------------------------------------------------------
    # DRAW DETECTION
    # -------------------------------------------------------

    def has_draw(self, my_cards, board):
        if not board:
            return False

        cards = my_cards + board
        suits = [c[1] for c in cards]

        # Flush draw
        for s in suits:
            if suits.count(s) == 4:
                return True

        return False

    # -------------------------------------------------------
    # PRESSURE RAISE
    # -------------------------------------------------------

    def pressure_raise(self, state, multiplier):
        pot = getattr(state, "pot", 40)
        min_r, max_r = state.raise_bounds
        target = int(pot * multiplier)
        return ActionRaise(min(max_r, max(min_r, target)))

    # -------------------------------------------------------
    # MAIN LOGIC
    # -------------------------------------------------------

    def get_move(self, game_info: GameInfo, state: PokerState):

        my_cards = state.my_hand
        board = getattr(state, "board", [])
        street = state.street
        pot = getattr(state, "pot", 40)
        cost = state.cost_to_call
        can_raise = state.can_act(ActionRaise)

        texture = self.evaluate_texture(board)
        hand_type = self.classify_hand(my_cards, board)
        draw = self.has_draw(my_cards, board)

        # -------------------------------------------------------
        # AUCTION
        # -------------------------------------------------------

        if street == "auction":
            chips = state.my_chips

            if draw or texture == "wet":
                bid = int(chips * 0.30)
            elif hand_type in ["overpair", "top_pair"]:
                bid = int(chips * 0.18)
            else:
                bid = int(chips * 0.05)

            return ActionBid(min(bid, chips))

        # -------------------------------------------------------
        # PREFLOP
        # -------------------------------------------------------

        if not board:

            r1 = self.rank_values[my_cards[0][0]]
            r2 = self.rank_values[my_cards[1][0]]

            if r1 == r2 or (r1 >= 11 and r2 >= 11):
                if can_raise:
                    return self.pressure_raise(state, 1.5)
                return ActionCall()

            if cost <= pot * 0.25:
                return ActionCall()

            return ActionFold()

        # -------------------------------------------------------
        # POSTFLOP STRATEGY
        # -------------------------------------------------------

        # -------- MONSTER / STRONG VALUE --------

        if hand_type in ["overpair"]:

            if can_raise:
                if texture == "wet":
                    return self.pressure_raise(state, 1.6)
                return self.pressure_raise(state, 1.2)

            return ActionCall()

        # -------- TOP PAIR VALUE --------

        if hand_type == "top_pair":

            if can_raise:
                return self.pressure_raise(state, 1.0)

            return ActionCall()

        # -------- MID PAIR CONTROL --------

        if hand_type == "mid_pair":

            if cost <= pot * 0.4:
                return ActionCall()

            return ActionFold()

        # -------- DRAWS (AGGRESSIVE SEMI BLUFF) --------

        if draw:

            if can_raise and random.random() < 0.65:
                return self.pressure_raise(state, 1.1)

            if cost <= pot * 0.45:
                return ActionCall()

            return ActionFold()

        # -------- AIR (CONTROLLED BLUFFING) --------

        if can_raise and random.random() < 0.35:
            return self.pressure_raise(state, 0.8)

        if state.can_act(ActionCheck):
            return ActionCheck()

        return ActionFold()


if __name__ == "__main__":
    run_bot(Player(), parse_args())