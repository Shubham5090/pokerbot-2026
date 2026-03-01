'''
Sneak Peek Hold'em - Log Manipulator Bot
Exploits fixed-bidding and fit-or-fold behaviors.
'''
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot

class Player(BaseBot):
    def __init__(self) -> None:
        self.rank_values = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, 
                            '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}

    def estimate_equity(self, my_cards, board):
        """Simple heuristic to detect if we have a strong hand or just air."""
        if not board:
            r1, r2 = self.rank_values[my_cards[0][0]], self.rank_values[my_cards[1][0]]
            return (r1 + r2) / 28.0 # Rough pre-flop strength
            
        my_ranks = [self.rank_values[c[0]] for c in my_cards]
        board_ranks = [self.rank_values[c[0]] for c in board]
        
        # Hit Top Pair or Overpair
        if my_ranks[0] in board_ranks or my_ranks[1] in board_ranks:
            return 0.75
        if my_ranks[0] == my_ranks[1] and my_ranks[0] > max(board_ranks):
            return 0.85
            
        return 0.3 # Pure air/trash

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        pass

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        pass

    def get_move(self, game_info: GameInfo, current_state: PokerState) -> ActionFold | ActionCall | ActionCheck | ActionRaise | ActionBid:
        my_cards = current_state.my_hand
        board = getattr(current_state, 'board', [])
        street = current_state.street
        pot = getattr(current_state, 'pot', 40)
        cost = current_state.cost_to_call
        
        can_raise = current_state.can_act(ActionRaise)
        min_raise, max_raise = current_state.raise_bounds if can_raise else (0, 0)
        
        eq = self.estimate_equity(my_cards, board)

        # ==========================================================
        # 1. THE LOG-EXPLOIT AUCTION PHASE
        # ==========================================================
        if street == 'auction':
            if eq > 0.70:
                # TRAP BID: We have a monster. We bid 987.
                # If 2_Patti bids 996, they win but pay 987 into the pot! We then stack them.
                # If This_is_embarrassing bids 10, we win and pay 10.
                return ActionBid(min(987, current_state.my_chips))
            else:
                # CHEAP PEEK: We have air. We bid 11.
                # Beats This_is_embarrassing's 10 bid, giving us cheap info.
                # If 2_Patti bids 996, they win and pay 11. We safely fold.
                return ActionBid(min(11, current_state.my_chips))

        # ==========================================================
        # 2. POST-FLOP EXPLOITATION
        # ==========================================================
        if board:
            # Exploit 1: If they check to us, they are weak. C-Bet aggressively.
            if can_raise and cost == 0:
                # Betting ~90% of the pot mimics the 37 into 40 bet that broke This_is_embarrassing
                target_bet = int(pot * 0.9)
                return ActionRaise(min(max_raise, max(min_raise, target_bet)))
            
            # Exploit 2: If they bet into us and we have a strong hand, trap/value them.
            if cost > 0:
                if eq > 0.70:
                    # 2_Patti is a calling station. If we have it, raise them to value town.
                    if can_raise: return ActionRaise(min(max_raise, max(min_raise, int(pot * 1.5))))
                    return ActionCall()
                # If we don't have it, respect the aggression and fold.
                return ActionFold() if current_state.can_act(ActionFold) else ActionCheck()
                
            if current_state.can_act(ActionCheck): return ActionCheck()

        # ==========================================================
        # 3. PRE-FLOP
        # ==========================================================
        if not board:
            if eq > 0.65: # Premium Hands
                if can_raise: return ActionRaise(min(max_raise, max(min_raise, 60)))
                return ActionCall()
            if cost <= 20: 
                return ActionCall() # Defend blinds
            return ActionFold() if current_state.can_act(ActionFold) else ActionCheck()

        # Fallback safety
        return ActionFold() if current_state.can_act(ActionFold) else ActionCheck()

if __name__ == '__main__':
    run_bot(Player(), parse_args())
