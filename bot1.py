
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot

import random

class Player(BaseBot):

    def hand_rank(cards):
        ranks = sorted([RANKS.index(c[0]) for c in cards], reverse=True)
        suits = [c[1] for c in cards]

        counts = {r: ranks.count(r) for r in set(ranks)}
        count_values = sorted(counts.values(), reverse=True)

        is_flush = len(set(suits)) == 1
        is_straight = len(set(ranks)) == 5 and max(ranks) - min(ranks) == 4

        if is_straight and is_flush:
            return (8, max(ranks))
        if 4 in count_values:
            return (7,)
        if 3 in count_values and 2 in count_values:
            return (6,)
        if is_flush:
            return (5, ranks)
        if is_straight:
            return (4, max(ranks))
        if 3 in count_values:
            return (3,)
        if count_values.count(2) == 2:
            return (2,)
        if 2 in count_values:
            return (1,)
        return (0, ranks)


    def best_hand(seven_cards):
        best = None
        for combo in itertools.combinations(seven_cards, 5):
            rank = hand_rank(combo)
            if best is None or rank > best:
                best = rank
        return best


    # -------------------------
    # % Win Predictor
    # -------------------------

    def win_probability_percent(current_state, simulations=300):

        my_hand = current_state.my_hand
        board = current_state.board

        deck = [r+s for r in RANKS for s in SUITS]
        known_cards = my_hand + board
        deck = [c for c in deck if c not in known_cards]

        wins = 0
        ties = 0

        for _ in range(simulations):
            random.shuffle(deck)

            opp_hand = deck[:2]

            needed = 5 - len(board)
            simulated_board = board + deck[2:2+needed]

            my_best = best_hand(my_hand + simulated_board)
            opp_best = best_hand(opp_hand + simulated_board)

            if my_best > opp_best:
                wins += 1
            elif my_best == opp_best:
                ties += 1

        win_rate = (wins + ties * 0.5) / simulations
        return win_rate * 100   # return percentage

        

    def __init__(self) -> None:
    
        pass

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        '''
        Called when a new round starts. Called NUM_ROUNDS times.

        Arguments:
        game_info: the GameInfo object.
        current_state: the PokerState object.

        Returns:
        Nothing.
        '''
        my_bankroll = game_info.bankroll  # the total number of chips you've gained or lost from the beginning of the game to the start of this round
        # the total number of seconds your bot has left to play this game
        time_bank = game_info.time_bank
        round_num = game_info.round_num  # the round number from 1 to NUM_ROUNDS
        
        # your cards
        # is an array; eg: ['Ah', 'Kd'] for Ace of hearts and King of diamonds
        my_cards = current_state.my_hand

        # opponent's  revealed cards or [] if not revealed
        opp_revealed_cards = current_state.opp_revealed_cards
        
        big_blind = current_state.is_bb  # True if you are the big blind
        pass

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        '''
        Called when a round ends. Called NUM_ROUNDS times.

        Arguments:
        game_info: the GameInfo object.
        current_state: the PokerState object.

        Returns:
        Nothing.
        '''
        my_delta = current_state.payoff  # your bankroll change from this round
        
        street = current_state.street  # 'pre-flop', 'flop', 'auction', 'turn', or 'river'
        # your cards
        # is an array; eg: ['Ah', 'Kd'] for Ace of hearts and King of diamonds
        my_cards = current_state.my_hand

        # opponent's revealed cards or [] if not revealed
        opp_revealed_cards = current_state.opp_revealed_cards
    def win_probability_with_known_card(current_state, simulations=300):
        """
        Returns win probability (%) when one opponent card is known.
        """

        my_hand = current_state.my_hand
        board = current_state.board

        # opponent revealed card
        if not current_state.opp_revealed_cards:
            return win_probability_percent(current_state, simulations)

        opp_known = current_state.opp_revealed_cards[0]

        # build deck
        deck = [r+s for r in RANKS for s in SUITS]

        known_cards = my_hand + board + [opp_known]
        deck = [c for c in deck if c not in known_cards]

        wins = 0
        ties = 0

        for _ in range(simulations):
            random.shuffle(deck)

            # opponent second card
            opp_second = deck[0]
            opp_hand = [opp_known, opp_second]

            # complete board
            needed = 5 - len(board)
            simulated_board = board + deck[1:1+needed]

            my_best = best_hand(my_hand + simulated_board)
            opp_best = best_hand(opp_hand + simulated_board)

            if my_best > opp_best:
                wins += 1
            elif my_best == opp_best:
                ties += 1

        win_rate = (wins + 0.5 * ties) / simulations
        return win_rate * 100

    def get_move(self, game_info: GameInfo, current_state: PokerState) -> ActionFold | ActionCall | ActionCheck | ActionRaise | ActionBid:
        '''
        Where the magic happens - your code should implement this function.
        Called any time the engine needs an action from your bot.

        Arguments:
        game_info: the GameInfo object.
        current_state: the PokerState object.

        Returns:
        Your action.
        '''

        if current_state.street == 'auction':
            win_pct = win_probability_percent(current_state, simulations=200)

            chips = current_state.my_chips

            # Bid logic based on win probability
            if 30 <= win_pct <= 50:
                bid_amount = int(0.25 * chips)
            else:
                bid_amount = 0   # don't bid otherwise

            return ActionBid(bid_amount)


        if current_state.opp_revealed_cards:
            # Looking at info from bid
            for card in current_state.opp_revealed_cards:
                # If opponent has a high card, we fold
                if ('A' in card) or ('K' in card) or ('Q' in card) or ('J' in card):
                    if current_state.can_act(ActionFold):
                        return ActionFold()
                    else:
                        return ActionCheck()

        if current_state.can_act(ActionRaise):
            # the smallest and largest numbers of chips for a legal bet/raise
            min_raise, max_raise = current_state.raise_bounds
            if random.random() < 0.5:
                return ActionRaise(min_raise)
        if current_state.can_act(ActionCheck):  # check-call
            return ActionCheck()
        if random.random() < 0.25:
            return ActionFold()
        return ActionCall()


if __name__ == '__main__':
    run_bot(Player(), parse_args())