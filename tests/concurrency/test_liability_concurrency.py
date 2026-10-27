"""Concurrency: one settlement per instruction, no double-spend under parallel checkouts."""
from decimal import Decimal

from agora.liability import BANK, MAKER, USER, DuplicateCheckout, LiabilityBook

AGENTS = {"shopping-agent": "asha"}


def book_with(instruction_id="c-1"):
    book = LiabilityBook(AGENTS)
    book.record({"instruction_id": instruction_id, "user": "asha", "item": "coffee grinder", "quantity": 1,
                 "merchant": "bean-shop", "limit": "2000.00"}, agent="shopping-agent")
    return book


def checkout(instruction_id="c-1"):
    return {"instruction_id": instruction_id, "user": "asha", "item": "espresso machine", "quantity": 1,
            "merchant": "bean-shop", "amount": "1200.00"}


def test_parallel_checkouts_on_one_instruction_settle_exactly_once():
    import threading
    from concurrent.futures import ThreadPoolExecutor

    book = book_with()
    barrier = threading.Barrier(8)
    refusals = []

    def settle(_):
        barrier.wait(timeout=10)
        try:
            return book.checkout(checkout(), actor="shopping-agent")
        except DuplicateCheckout as refused:
            refusals.append(refused)
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        awards = [award for award in pool.map(settle, range(8)) if award is not None]

    assert len(awards) == 1 and len(refusals) == 7
    assert book.settled_count() == 1 and book.instruction_count() == 1
    assert book.totals() == {USER: Decimal("0.00"), MAKER: Decimal("1200.00"), BANK: Decimal("0.00")}
    assert all(refused.award == awards[0] for refused in refusals)


def test_parallel_checkouts_on_different_instructions_all_settle():
    from concurrent.futures import ThreadPoolExecutor

    book = LiabilityBook(AGENTS)
    for n in range(8):
        book.record({"instruction_id": "c-%d" % n, "user": "asha", "item": "coffee grinder", "quantity": 1,
                     "merchant": "bean-shop", "limit": "2000.00"}, agent="shopping-agent")

    with ThreadPoolExecutor(max_workers=8) as pool:
        awards = list(pool.map(lambda n: book.checkout(checkout("c-%d" % n), actor="shopping-agent"), range(8)))
    assert len(awards) == 8 and {award.party for award in awards} == {MAKER}
    assert book.settled_count() == 8
    assert book.totals()[MAKER] == Decimal("9600.00")  # 8 x 1200.00, charged once each
