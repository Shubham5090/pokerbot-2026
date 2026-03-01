import eval7
import time
import random

deck = eval7.Deck()
hand = [eval7.Card("As"), eval7.Card("Ks")]
board = [eval7.Card("2h"), eval7.Card("3h"), eval7.Card("4h")]

t0 = time.time()
for _ in range(300):
    d = eval7.Deck()
    for c in hand + board:
        d.cards.remove(c)
    d.shuffle()
    b = board + d.cards[:2]
    o = d.cards[2:4]
    v1 = eval7.evaluate(hand + b)
    v2 = eval7.evaluate(o + b)
t1 = time.time()
print(f"Time for 300 MC loops: {(t1-t0)*1000:.2f} ms")
