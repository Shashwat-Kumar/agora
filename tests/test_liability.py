"""Who pays when an AI agent's purchase goes wrong: the rule from open debate #22.

The hard case is a purchase that stays inside the agent's spending limit but is not what
the customer meant. See docs/LIABILITY.md for the debate turns each behaviour cites.
"""
import json
from decimal import Decimal

import pytest

from agora.liability import (
    BANK,
    CENT,
    MAKER,
    USER,
    DuplicateCheckout,
    EmptyInstruction,
    Instruction,
    InvalidPurchase,
    LiabilityBook,
    LiabilityError,
    LimitExceeded,
    MalformedInstruction,
    Purchase,
    UnauthorisedCaller,
    UnknownInstruction,
    adjudicate_request,
    decide,
    explain,
)

AGENTS = {"shopping-agent": "asha"}


def instruction_request(**over):
    data = {"instruction_id": "i-1", "user": "asha", "item": "coffee grinder",
            "quantity": 1, "merchant": "bean-shop", "limit": "2000.00"}
    data.update(over)
    return data


def checkout_request(**over):
    data = {"instruction_id": "i-1", "user": "asha", "item": "coffee grinder",
            "quantity": 1, "merchant": "bean-shop", "amount": "120.00"}
    data.update(over)
    return data


def new_book():
    book = LiabilityBook(AGENTS)
    book.record(instruction_request(), agent="shopping-agent")
    return book


# --------------------------------------------------------------- the rule itself

def test_user_pays_when_the_purchase_matches_the_logged_instruction():
    award = new_book().checkout(checkout_request(), actor="shopping-agent")
    assert award.party == USER and award.cause == "matches_logged_instruction"
    assert (award.user_pays, award.maker_pays, award.bank_pays) == (Decimal("120.00"), Decimal("0.00"), Decimal("0.00"))
    assert award.cap == Decimal("2000.00") and award.settled_by == BANK


def test_maker_pays_when_the_item_deviates_inside_the_limit():
    award = new_book().checkout(checkout_request(item="espresso machine", amount="1200.00"), actor="shopping-agent")
    assert award.party == MAKER and award.deviations == ("item",)
    assert award.maker_pays == Decimal("1200.00") and award.user_pays == Decimal("0.00")
    assert "the maker" in award.rule and "#2" in award.rule and "#6" in award.rule


def test_quantity_and_merchant_deviations_also_hit_the_maker():
    for field, value in (("quantity", 3), ("merchant", "other-shop")):
        award = new_book().checkout(checkout_request(**{field: value}), actor="shopping-agent")
        assert award.party == MAKER and award.deviations == (field,), (field, award)


def test_user_pays_again_when_the_user_approves_after_the_fact():
    award = new_book().checkout(checkout_request(item="espresso machine", approved_by="asha"), actor="shopping-agent")
    assert award.party == USER and award.cause == "approved_after_the_fact"


def test_bank_never_absorbs_a_within_limit_purchase():
    book = new_book()
    awards = [book.checkout(checkout_request(instruction_id="i-1"), actor="shopping-agent")]
    book.record(instruction_request(instruction_id="i-2"), agent="shopping-agent")
    awards.append(book.checkout(checkout_request(instruction_id="i-2", item="espresso machine", amount="900.00"),
                                actor="shopping-agent"))
    assert all(a.bank_pays == Decimal("0.00") and a.settled_by == BANK for a in awards)
    assert book.totals()[BANK] == Decimal("0.00")
    assert book.totals()[USER] == Decimal("120.00") and book.totals()[MAKER] == Decimal("900.00")


def test_decide_is_pure_and_replayable():
    instruction = Instruction.from_mapping(instruction_request(), agent="shopping-agent")
    purchase = Purchase.from_mapping(checkout_request(item="espresso machine", amount="1200.00"))
    first = decide(instruction, purchase, checkout_id="receipt-7")
    second = decide(instruction, purchase, checkout_id="receipt-7")
    assert first == second and first.checkout_id == "receipt-7"
    assert first.amount == Decimal("1200.00") and isinstance(first.maker_pays, Decimal)


# --------------------------------------------------------------- boundaries

def test_allowed_charges_are_the_half_open_interval_up_to_the_limit():
    award = new_book().checkout(checkout_request(amount="2000.00"), actor="shopping-agent")
    assert award.party == USER and award.cap == Decimal("2000.00")
    minute = new_book()
    minute.record(instruction_request(instruction_id="i-2", limit="0.01"), agent="shopping-agent")
    assert minute.checkout(checkout_request(instruction_id="i-2", amount="0.01"), actor="shopping-agent").cap == CENT


def test_one_cent_above_the_limit_is_refused_and_settles_nothing():
    book = new_book()
    with pytest.raises(LimitExceeded) as raised:
        book.checkout(checkout_request(amount="2000.01"), actor="shopping-agent")
    assert raised.value.code == "limit_exceeded" and raised.value.field == "amount"
    assert book.settlement("i-1") is None and book.settled_count() == 0
    assert book.totals() == {USER: Decimal("0.00"), MAKER: Decimal("0.00"), BANK: Decimal("0.00")}


def test_quantity_boundary_is_one_and_zero_is_refused():
    assert Instruction.from_mapping(instruction_request(quantity=1), agent="a").quantity == 1
    with pytest.raises(MalformedInstruction):
        Instruction.from_mapping(instruction_request(quantity=0), agent="a")
    with pytest.raises(MalformedInstruction):
        Instruction.from_mapping(instruction_request(quantity=-3), agent="a")


def test_limits_below_one_cent_and_extra_precision_are_refused():
    for bad in ("0", "0.001", 0):
        with pytest.raises(MalformedInstruction):
            Instruction.from_mapping(instruction_request(limit=bad), agent="a")
    with pytest.raises(MalformedInstruction):
        Purchase.from_mapping(checkout_request(amount="12.345"))


# --------------------------------------------------------------- null and empty input

def test_null_arguments_raise_typed_errors_not_crashes():
    book = new_book()
    with pytest.raises(EmptyInstruction):
        book.record(None, agent="shopping-agent")
    with pytest.raises(InvalidPurchase):
        book.checkout(None, actor="shopping-agent")
    with pytest.raises(EmptyInstruction):
        LiabilityBook(None)
    with pytest.raises(MalformedInstruction):
        decide(None, None)
    with pytest.raises(EmptyInstruction):
        Instruction.from_mapping(None, agent="shopping-agent")
    with pytest.raises(EmptyInstruction):
        Instruction.from_mapping(None, agent=None)


def test_blank_and_empty_fields_are_rejected_with_diagnostics():
    for field in ("instruction_id", "user", "item", "merchant"):
        with pytest.raises(EmptyInstruction) as raised:
            Instruction.from_mapping(instruction_request(**{field: "   "}), agent="a")
        assert raised.value.field == field and field in str(raised.value)
    with pytest.raises(EmptyInstruction):
        Instruction.from_mapping(instruction_request(limit=""), agent="a")
    with pytest.raises(EmptyInstruction):
        Purchase.from_mapping(checkout_request(amount=""))
    with pytest.raises(EmptyInstruction):
        LiabilityBook({})


def test_empty_collections_and_non_objects_are_rejected():
    with pytest.raises(MalformedInstruction):
        Instruction.from_mapping([], agent="a")
    with pytest.raises(MalformedInstruction):
        Purchase.from_mapping("not an object")
    with pytest.raises(MalformedInstruction):
        LiabilityBook(["a", "b"])
    with pytest.raises(EmptyInstruction):
        Purchase.from_mapping({})
    with pytest.raises(UnauthorisedCaller):
        LiabilityBook(AGENTS).record(instruction_request(), agent="a")


# --------------------------------------------------------------- refusal paths

def test_malformed_values_are_refused_with_a_code():
    for bad in ("abc", "NaN", "Infinity", True, object()):
        with pytest.raises(MalformedInstruction) as raised:
            Purchase.from_mapping(checkout_request(amount=bad))
        assert raised.value.code == "malformed_instruction" and raised.value.field == "amount"
    with pytest.raises(MalformedInstruction):
        Purchase.from_mapping(checkout_request(quantity="2"))
    with pytest.raises(EmptyInstruction):
        Purchase.from_mapping({k: v for k, v in checkout_request().items() if k != "amount"})


def test_unauthorised_callers_are_refused():
    book = LiabilityBook({"shopping-agent": "asha", "finance-agent": "ravi"})
    with pytest.raises(UnauthorisedCaller) as raised:
        book.record(instruction_request(), agent="unregistered-agent")
    assert raised.value.code == "unauthorised_caller"
    with pytest.raises(UnauthorisedCaller):
        book.record(instruction_request(), agent="finance-agent")  # acts for ravi, not asha
    book.record(instruction_request(), agent="shopping-agent")
    for bad_actor in (None, "", "  ", "finance-agent"):
        with pytest.raises(UnauthorisedCaller):
            book.checkout(checkout_request(), actor=bad_actor)
    assert book.settled_count() == 0
    with pytest.raises(UnauthorisedCaller):
        book.checkout(checkout_request(user="ravi"), actor="shopping-agent")


def test_unknown_instruction_and_third_party_approval_are_refused():
    with pytest.raises(UnknownInstruction) as raised:
        new_book().checkout(checkout_request(instruction_id="i-404"), actor="shopping-agent")
    assert raised.value.code == "unknown_instruction"
    with pytest.raises(UnauthorisedCaller):
        new_book().checkout(checkout_request(item="espresso machine", approved_by="ravi"), actor="shopping-agent")


def test_a_second_identical_instruction_id_is_refused():
    book = new_book()
    with pytest.raises(MalformedInstruction):
        book.record(instruction_request(), agent="shopping-agent")



# --------------------------------------------------------------- concurrency

def test_simultaneous_checkouts_settle_once_and_never_double_spend():
    import threading
    from concurrent.futures import ThreadPoolExecutor

    book = new_book()
    barrier = threading.Barrier(8)
    refusals = []

    def settle(_):
        barrier.wait(timeout=10)
        try:
            return book.checkout(checkout_request(item="espresso machine", amount="1200.00"),
                                 actor="shopping-agent")
        except DuplicateCheckout as refused:
            refusals.append(refused)
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        awards = [award for award in pool.map(settle, range(8)) if award is not None]
    assert len(awards) == 1 and len(refusals) == 7
    assert book.totals()[MAKER] == Decimal("1200.00")  # charged once, not eight times
    assert book.totals()[USER] == Decimal("0.00") and book.settled_count() == 1
    assert all(refused.award == awards[0] for refused in refusals)


def test_distinct_instructions_settle_independently_under_load():
    from concurrent.futures import ThreadPoolExecutor

    book = LiabilityBook(AGENTS)
    for n in range(8):
        book.record(instruction_request(instruction_id="i-%d" % n, limit="500.00"), agent="shopping-agent")

    def settle(n):
        return book.checkout(checkout_request(instruction_id="i-%d" % n, item="wrong item", amount="100.00"),
                             actor="shopping-agent")

    with ThreadPoolExecutor(max_workers=8) as pool:
        awards = list(pool.map(settle, range(8)))
    assert book.settled_count() == 8 and {award.party for award in awards} == {MAKER}
    assert book.totals()[MAKER] == Decimal("800.00")


# --------------------------------------------------------------- request, CLI, codes

def test_adjudicate_request_reports_an_award_or_a_typed_error():
    ok = adjudicate_request({"agents": AGENTS, "agent": "shopping-agent",
                             "instruction": instruction_request(),
                             "checkout": checkout_request(item="espresso machine", amount="1200.00")})
    assert ok["award"]["party"] == MAKER and ok["award"]["maker_pays"] == "1200.00"
    assert ok["book"]["totals"]["bank"] == "0.00" and "#6" in ok["explain"]
    assert adjudicate_request(None)["error"] == "empty_instruction"
    assert adjudicate_request({"agents": AGENTS, "agent": "shopping-agent",
                               "instruction": instruction_request(),
                               "checkout": None})["error"] == "invalid_purchase"
    unauthorised = adjudicate_request({"agents": AGENTS, "agent": "nobody",
                                       "instruction": instruction_request(), "checkout": checkout_request()})
    assert unauthorised["error"] == "unauthorised_caller"


def test_cli_liability_end_to_end(tmp_path, capsys):
    from agora.cli import main

    path = tmp_path / "request.json"
    path.write_text(json.dumps({"agents": AGENTS, "agent": "shopping-agent",
                                "instruction": instruction_request(),
                                "checkout": checkout_request(item="espresso machine", amount="1200.00")}))
    assert main(["liability", str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["award"]["party"] == MAKER and payload["award"]["maker_pays"] == "1200.00"

    path.write_text(json.dumps({"agents": AGENTS, "agent": "shopping-agent",
                                "instruction": instruction_request(limit="100.00"),
                                "checkout": checkout_request(amount="100.01")}))
    assert main(["liability", str(path)]) == 2
    assert json.loads(capsys.readouterr().out)["error"] == "limit_exceeded"


def test_error_codes_are_stable_typed_and_serialisable():
    expected = {
        EmptyInstruction: "empty_instruction",
        MalformedInstruction: "malformed_instruction",
        InvalidPurchase: "invalid_purchase",
        LimitExceeded: "limit_exceeded",
        UnauthorisedCaller: "unauthorised_caller",
        UnknownInstruction: "unknown_instruction",
        DuplicateCheckout: "duplicate_checkout",
    }
    for cls, code in expected.items():
        error = cls("refused")
        assert issubclass(cls, LiabilityError) and issubclass(cls, ValueError)
        assert error.code == code == error.as_dict()["error"]
        assert error.as_dict()["message"] == "refused" and "field" in error.as_dict()


def test_award_serialises_to_strings_and_explains_itself():
    award = new_book().checkout(checkout_request(item="espresso machine", amount="1200.00"),
                                actor="shopping-agent")
    payload = award.as_dict()
    assert payload["party"] == MAKER and payload["cap"] == "2000.00" and payload["settled_by"] == BANK
    assert all(isinstance(payload[key], str) for key in ("amount", "user_pays", "maker_pays", "bank_pays"))
    text = explain(award)
    assert "maker" in text and "2000.00" in text and "bank" in text
    assert "user pays" in explain(new_book().checkout(checkout_request(), actor="shopping-agent"))

