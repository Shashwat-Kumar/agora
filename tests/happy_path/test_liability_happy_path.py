"""Happy path: a purchase that follows the logged instruction settles normally."""
from decimal import Decimal

from agora.liability import BANK, MAKER, USER, LiabilityBook

AGENTS = {"shopping-agent": "asha"}


def test_checked_out_instruction_within_limit_completes_and_settles_once():
    book = LiabilityBook(AGENTS)
    instruction = book.record(
        {"instruction_id": "happy-1", "user": "asha", "item": "coffee grinder", "quantity": 1,
         "merchant": "bean-shop", "limit": "2000.00"},
        agent="shopping-agent",
    )
    assert instruction.limit == Decimal("2000.00") and book.instruction_count() == 1

    award = book.checkout(
        {"instruction_id": "happy-1", "user": "asha", "item": "coffee grinder", "quantity": 1,
         "merchant": "bean-shop", "amount": "120.00"},
        actor="shopping-agent",
    )
    assert award.party == USER and award.cause == "matches_logged_instruction"
    assert award.user_pays == Decimal("120.00") and award.maker_pays == Decimal("0.00")
    assert award.bank_pays == Decimal("0.00") and award.settled_by == BANK
    assert book.settlement("happy-1") == award and book.settled_count() == 1
    assert book.totals() == {USER: Decimal("120.00"), MAKER: Decimal("0.00"), BANK: Decimal("0.00")}


def test_the_same_payload_through_the_stateless_entry_point_succeeds():
    from agora.liability import adjudicate_request

    result = adjudicate_request({
        "agents": AGENTS, "agent": "shopping-agent",
        "instruction": {"instruction_id": "happy-2", "user": "asha", "item": "coffee grinder",
                        "quantity": 1, "merchant": "bean-shop", "limit": "2000.00"},
        "checkout": {"instruction_id": "happy-2", "user": "asha", "item": "coffee grinder",
                     "quantity": 1, "merchant": "bean-shop", "amount": "120.00"},
    })
    assert result["award"]["party"] == USER and result["award"]["user_pays"] == "120.00"
    assert result["book"]["totals"]["user"] == "120.00"
