"""Boundary: allowed charges are (0, limit]; one cent above the limit is refused."""
from decimal import Decimal

import pytest

from agora.liability import CENT, USER, Instruction, LimitExceeded, LiabilityBook, MalformedInstruction

AGENTS = {"shopping-agent": "asha"}


def book_with(limit="2000.00"):
    book = LiabilityBook(AGENTS)
    book.record({"instruction_id": "b-1", "user": "asha", "item": "coffee grinder", "quantity": 1,
                 "merchant": "bean-shop", "limit": limit}, agent="shopping-agent")
    return book


def test_exactly_the_limit_is_inside_the_half_open_interval():
    award = book_with().checkout({"instruction_id": "b-1", "user": "asha", "item": "coffee grinder",
                                  "quantity": 1, "merchant": "bean-shop", "amount": "2000.00"},
                                 actor="shopping-agent")
    assert award.party == USER and award.cap == Decimal("2000.00")


def test_one_cent_over_the_limit_is_refused_at_the_boundary():
    with pytest.raises(LimitExceeded) as raised:
        book_with().checkout({"instruction_id": "b-1", "user": "asha", "item": "coffee grinder",
                              "quantity": 1, "merchant": "bean-shop", "amount": "2000.01"},
                             actor="shopping-agent")
    assert raised.value.code == "limit_exceeded" and raised.value.field == "amount"


def test_lower_bounds_of_quantity_and_limit():
    assert Instruction.from_mapping({"instruction_id": "b-2", "user": "asha", "item": "pin",
                                     "quantity": 1, "merchant": "shop", "limit": "0.01"},
                                    agent="a").limit == CENT
    award = book_with("0.01").checkout({"instruction_id": "b-1", "user": "asha", "item": "coffee grinder",
                                        "quantity": 1, "merchant": "bean-shop", "amount": "0.01"},
                                       actor="shopping-agent")
    assert award.user_pays == CENT
    for bad_limit in ("0", "-1", "0.001"):
        with pytest.raises(MalformedInstruction):
            Instruction.from_mapping({"instruction_id": "b-3", "user": "asha", "item": "pin",
                                      "quantity": 1, "merchant": "shop", "limit": bad_limit}, agent="a")
