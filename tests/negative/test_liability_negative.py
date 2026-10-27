"""Negative: malformed payloads and unauthorised callers are refused immediately."""
from decimal import Decimal

import pytest

from agora.liability import (
    BANK,
    MAKER,
    USER,
    DuplicateCheckout,
    EmptyInstruction,
    InvalidPurchase,
    LiabilityBook,
    MalformedInstruction,
    UnauthorisedCaller,
    UnknownInstruction,
)

AGENTS = {"shopping-agent": "asha"}


def new_book():
    book = LiabilityBook(AGENTS)
    book.record({"instruction_id": "n-1", "user": "asha", "item": "coffee grinder", "quantity": 1,
                 "merchant": "bean-shop", "limit": "2000.00"}, agent="shopping-agent")
    return book


def checkout(**over):
    data = {"instruction_id": "n-1", "user": "asha", "item": "coffee grinder", "quantity": 1,
            "merchant": "bean-shop", "amount": "120.00"}
    data.update(over)
    return data


def test_malformed_payloads_are_refused_with_a_typed_code():
    for bad in ("not-an-amount", "NaN", True):
        with pytest.raises(MalformedInstruction) as raised:
            new_book().checkout(checkout(amount=bad), actor="shopping-agent")
        assert raised.value.code == "malformed_instruction"
    with pytest.raises(InvalidPurchase):
        new_book().checkout(None, actor="shopping-agent")
    with pytest.raises(MalformedInstruction):
        new_book().checkout("{\"amount\": 1}", actor="shopping-agent")
    with pytest.raises(EmptyInstruction):
        LiabilityBook({})


def test_unauthorised_agents_and_actors_are_refused_without_state_change():
    book = LiabilityBook({"shopping-agent": "asha", "finance-agent": "ravi"})
    with pytest.raises(UnauthorisedCaller):
        book.record({"instruction_id": "n-2", "user": "asha", "item": "grinder", "quantity": 1,
                     "merchant": "bean-shop", "limit": "100.00"}, agent="finance-agent")
    book.record({"instruction_id": "n-2", "user": "asha", "item": "grinder", "quantity": 1,
                 "merchant": "bean-shop", "limit": "100.00"}, agent="shopping-agent")
    with pytest.raises(UnauthorisedCaller):
        book.checkout(checkout(instruction_id="n-2"), actor="finance-agent")
    with pytest.raises(UnauthorisedCaller):
        book.checkout(checkout(instruction_id="n-2"), actor=None)
    with pytest.raises(UnknownInstruction):
        book.checkout(checkout(instruction_id="missing"), actor="shopping-agent")
    assert book.settled_count() == 0
    assert book.totals() == {USER: Decimal("0.00"), MAKER: Decimal("0.00"), BANK: Decimal("0.00")}


def test_a_replayed_checkout_is_refused_rather_than_charged_twice():
    book = new_book()
    first = book.checkout(checkout(), actor="shopping-agent")
    with pytest.raises(DuplicateCheckout) as raised:
        book.checkout(checkout(), actor="shopping-agent")
    assert raised.value.code == "duplicate_checkout" and raised.value.award == first
    assert book.totals()[USER] == Decimal("120.00")
