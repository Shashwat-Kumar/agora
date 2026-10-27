"""Regression for issue #22: an agent's within-limit purchase that the user did not mean.

The debate's hard case: the agent stays inside the spending limit but buys something the
customer did not mean. Before this rule existed the repository had no answer at all, and
turn #5's flat, capped reimbursement would have left the user exposed above the cap. The
rule that resolves it: the maker refunds a purchase that deviates from the logged
instruction, bounded by the user's own limit (turn #6), with the bank only settling.
"""
from decimal import Decimal

from agora.liability import BANK, CENT, MAKER, USER, LiabilityBook, decide, Instruction, Purchase

AGENTS = {"shopping-agent": "asha"}
FLAT_CAP_FROM_TURN_5 = Decimal("500.00")


def settled(hard_case_item="espresso machine", hard_case_amount="1200.00", limit="2000.00"):
    book = LiabilityBook(AGENTS)
    book.record({"instruction_id": "issue-22", "user": "asha", "item": "coffee grinder", "quantity": 1,
                 "merchant": "bean-shop", "limit": limit}, agent="shopping-agent")
    return book, book.checkout({"instruction_id": "issue-22", "user": "asha", "item": hard_case_item,
                                "quantity": 1, "merchant": "bean-shop", "amount": hard_case_amount},
                               actor="shopping-agent")


def test_within_limit_purchase_the_user_did_not_mean_is_the_makers_loss():
    book, award = settled()
    assert award.party == MAKER
    assert award.maker_pays == Decimal("1200.00") and award.user_pays == Decimal("0.00")
    assert award.bank_pays == Decimal("0.00") and award.settled_by == BANK
    assert book.settlement("issue-22") == award


def test_the_users_limit_is_the_reimbursement_cap_not_a_flat_cap():
    _, award = settled()
    assert award.cap == Decimal("2000.00") and award.maker_pays > FLAT_CAP_FROM_TURN_5
    assert award.maker_pays == min(award.amount, award.cap)
    assert "#6" in award.rule  # cites the turn that rejected the flat cap


def test_the_user_pays_only_when_the_purchase_matches_the_logged_instruction():
    book, _ = settled()
    instruction = Instruction.from_mapping({"instruction_id": "issue-22", "user": "asha", "item": "coffee grinder",
                                            "quantity": 1, "merchant": "bean-shop", "limit": "2000.00"},
                                           agent="shopping-agent")
    matching = decide(instruction, Purchase.from_mapping(
        {"instruction_id": "issue-22", "user": "asha", "item": "coffee grinder", "quantity": 1,
         "merchant": "bean-shop", "amount": "120.00"}))
    assert matching.party == USER and book.totals()[USER] == Decimal("0.00")


def test_a_ten_cent_deviation_is_still_the_makers_loss():
    book, award = settled(limit="0.50", hard_case_amount="0.10", hard_case_item="other grinder")
    assert award.party == MAKER and award.maker_pays == CENT * 10
