import random
import itertools

RANKS = "23456789TJQKA"
SUITS = "dsch"


# =====================================================
# Hand Evaluator
# =====================================================

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


# =====================================================
# Win Probability
# =====================================================

def win_probability_percent(my_hand, board, simulations=500):

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

    win_rate = (wins + 0.5 * ties) / simulations
    return win_rate * 100


# =====================================================
# Deal Cards Step-by-Step
# =====================================================

def deal_game(my_hand):

    deck = [r+s for r in RANKS for s in SUITS]
    deck = [c for c in deck if c not in my_hand]
    random.shuffle(deck)

    board = []

    print("\n=== PREFLOP ===")
    print("Hand:", my_hand)
    print("Win %:", round(win_probability_percent(my_hand, board), 2))

    # FLOP (3 cards)
    board += deck[:3]
    print("\n=== FLOP ===")
    print("Board:", board)
    print("Win %:", round(win_probability_percent(my_hand, board), 2))

    # TURN (1 card)
    board += [deck[3]]
    print("\n=== TURN ===")
    print("Board:", board)
    print("Win %:", round(win_probability_percent(my_hand, board), 2))

    # RIVER (1 card)
    board += [deck[4]]
    print("\n=== RIVER ===")
    print("Board:", board)
    print("Win %:", round(win_probability_percent(my_hand, board), 2))


# =====================================================
# MAIN
# =====================================================

if __name__ == "__main__":

    print("Enter your two cards (example: Ah Ks)")
    cards = input("Your hand: ").split()

    deal_game(cards)