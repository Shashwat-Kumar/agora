"""Who pays when an AI agent's purchase goes wrong?

The rule in code, taken from the Agora open debate of 27 Oct 2026 (issue #22, turns
#1-#8). The hard case is a purchase that stays *inside* the agent's spending limit but
buys something the customer did not mean:

* The agent records the user's instruction before checkout: item, quantity, merchant and
  the user's own spending limit (Claude, #2).
* The maker carries the loss when the completed purchase deviates from that record on
  item, quantity or merchant (Claude, #2; GPT accepts capped make-good in #5).
* The user-chosen limit is the reimbursement cap, not a flat cap, so the maker's exposure
  is bounded by the limit the user set (Claude, #6).
* The user pays only when the purchase matches the logged instruction, or when the user
  approves the deviation afterwards (Claude, #2).
* The bank settles and reverses; it absorbs nothing while the purchase stayed inside the
  limit (GPT, #5: a cap stops overspending, not a wrong purchase).
* A charge above the limit is a rails failure, so this module refuses it with a typed
  error instead of guessing who pays (GPT, #1, #5).

Nothing here moves real money. It decides who owes what, deterministically and once per
instruction, so a settlement system or a human can act on the decision. Amounts are in one
currency and always whole cents.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Optional, Tuple

USER = "user"
MAKER = "maker"
BANK = "bank"
CENT = Decimal("0.01")
ZERO = Decimal("0.00")
DEVIATION_FIELDS = ("item", "quantity", "merchant")

# Each decision cites the debate turn it comes from, so the code carries its own source.
RULE_INSTRUCTION_LOG = "#2 Claude: record the user's instruction before checkout"
RULE_USER_MATCHES = "#2 Claude: the user pays only when the purchase matches the record"
RULE_MAKER_DEVIATES = "#2 Claude: the maker is liable when the purchase deviates"
RULE_LIMIT_CAP = "#6 Claude: the user-chosen limit is the reimbursement cap, not a flat cap"
RULE_BANK_SETTLES = "#5 GPT: a cap stops overspending, not a wrong purchase; the bank settles"


class LiabilityError(ValueError):
    """Typed refusal. `code` is stable, `field` names the offending input."""

    code = "liability_error"

    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.field = field

    def as_dict(self) -> dict:
        return {"error": self.code, "message": str(self), "field": self.field}


class EmptyInstruction(LiabilityError):
    """A required field was missing, None or blank."""

    code = "empty_instruction"


class MalformedInstruction(LiabilityError):
    """A field was present but not a value the ledger can use."""

    code = "malformed_instruction"


class InvalidPurchase(LiabilityError):
    """The checkout itself was missing or not an object."""

    code = "invalid_purchase"


class LimitExceeded(LiabilityError):
    """The charge is above the user's limit: the rails should have blocked it."""

    code = "limit_exceeded"


class UnauthorisedCaller(LiabilityError):
    """An actor tried to act for a user or agent it is not registered for."""

    code = "unauthorised_caller"


class UnknownInstruction(LiabilityError):
    """No instruction was recorded for this checkout."""

    code = "unknown_instruction"


class DuplicateCheckout(LiabilityError):
    """This instruction is already settled; settling again would double-spend."""

    code = "duplicate_checkout"

    def __init__(self, message: str, field: Optional[str] = None, award: Optional["Award"] = None):
        super().__init__(message, field)
        self.award = award


def _text(value, field: str) -> str:
    if value is None:
        raise EmptyInstruction(f"{field} is required", field)
    if isinstance(value, bool) or not isinstance(value, str):
        raise MalformedInstruction(f"{field} must be a string", field)
    cleaned = value.strip()
    if not cleaned:
        raise EmptyInstruction(f"{field} must not be blank", field)
    return cleaned


def _quantity(value, field: str = "quantity") -> int:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise EmptyInstruction(f"{field} is required", field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MalformedInstruction(f"{field} must be a whole number", field)
    if value < 1:
        raise MalformedInstruction(f"{field} must be at least 1", field)
    return value


@dataclass(frozen=True)
class Instruction:
    """What the user told the agent to buy, recorded before checkout."""

    instruction_id: str
    user: str
    item: str
    quantity: int
    merchant: str
    limit: Decimal
    agent: str

    @classmethod
    def from_mapping(cls, request, *, agent) -> "Instruction":
        agent = _text(agent, "agent")
        if request is None:
            raise EmptyInstruction("instruction is required", "instruction")
        if not isinstance(request, Mapping):
            raise MalformedInstruction("instruction must be an object", "instruction")
        return cls(
            instruction_id=_text(request.get("instruction_id"), "instruction_id"),
            user=_text(request.get("user"), "user"),
            item=_text(request.get("item"), "item"),
            quantity=_quantity(request.get("quantity")),
            merchant=_text(request.get("merchant"), "merchant"),
            limit=_money(request.get("limit"), "limit", minimum=CENT),
            agent=agent,
        )


@dataclass(frozen=True)
class Purchase:
    """The checkout the bank charged, with the instruction it claims to follow."""

    instruction_id: str
    user: str
    item: str
    quantity: int
    merchant: str
    amount: Decimal
    approved_by: Optional[str] = None

    @classmethod
    def from_mapping(cls, request, *, instruction_id: Optional[str] = None) -> "Purchase":
        if request is None:
            raise InvalidPurchase("checkout is required", "checkout")
        if not isinstance(request, Mapping):
            raise MalformedInstruction("checkout must be an object", "checkout")
        approved = request.get("approved_by")
        if approved is not None:
            approved = _text(approved, "approved_by")
        return cls(
            instruction_id=_text(request.get("instruction_id", instruction_id), "instruction_id"),
            user=_text(request.get("user"), "user"),
            item=_text(request.get("item"), "item"),
            quantity=_quantity(request.get("quantity")),
            merchant=_text(request.get("merchant"), "merchant"),
            amount=_money(request.get("amount"), "amount", minimum=CENT),
            approved_by=approved,
        )


@dataclass(frozen=True)
class Award:
    """Who carries the loss for one settled checkout."""

    checkout_id: str
    instruction_id: str
    party: str
    amount: Decimal
    user_pays: Decimal
    maker_pays: Decimal
    bank_pays: Decimal
    cause: str
    rule: str
    cap: Optional[Decimal] = None
    deviations: Tuple[str, ...] = ()
    settled_by: str = BANK

    def as_dict(self) -> dict:
        return {
            "checkout_id": self.checkout_id,
            "instruction_id": self.instruction_id,
            "party": self.party,
            "amount": str(self.amount),
            "user_pays": str(self.user_pays),
            "maker_pays": str(self.maker_pays),
            "bank_pays": str(self.bank_pays),
            "cause": self.cause,
            "rule": self.rule,
            "cap": str(self.cap) if self.cap is not None else None,
            "deviations": list(self.deviations),
            "settled_by": self.settled_by,
        }


def _money(value, field: str, minimum: Optional[Decimal] = None) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise EmptyInstruction(f"{field} is required", field)
    if isinstance(value, bool):
        raise MalformedInstruction(f"{field} must be an amount, not a boolean", field)
    if isinstance(value, Decimal):
        amount = value
    else:
        try:
            amount = Decimal(str(value).strip())
        except (InvalidOperation, ValueError, AttributeError, TypeError):
            raise MalformedInstruction(f"{field} must be a decimal amount", field) from None
    if not amount.is_finite():
        raise MalformedInstruction(f"{field} must be a finite amount", field)
    if amount.as_tuple().exponent < -2:
        raise MalformedInstruction(f"{field} must be a whole number of cents", field)
    if minimum is not None and amount < minimum:
        raise MalformedInstruction(f"{field} must be at least {minimum}", field)
    return amount


def decide(instruction: Instruction, purchase: Purchase, checkout_id: Optional[str] = None) -> Award:
    """The rule itself, with no state, so any decision can be replayed or appealed."""
    if not isinstance(instruction, Instruction) or not isinstance(purchase, Purchase):
        raise MalformedInstruction("decide() needs an Instruction and a Purchase", "instructions")
    if purchase.amount > instruction.limit:
        raise LimitExceeded(
            f"charge of {purchase.amount} is above the user's limit of {instruction.limit}: "
            "the payment rails should have refused it, so this ledger does not decide who pays",
            "amount",
        )
    deviations = tuple(f for f in DEVIATION_FIELDS if getattr(purchase, f) != getattr(instruction, f))
    if deviations and purchase.approved_by is not None:
        if purchase.approved_by != instruction.user:
            raise UnauthorisedCaller("only the user can approve a deviating purchase", "approved_by")
        party, cause = USER, "approved_after_the_fact"
    elif deviations:
        party, cause = MAKER, "deviation:" + ",".join(deviations)
    else:
        party, cause = USER, "matches_logged_instruction"
    if party == MAKER:
        rule = f"{RULE_MAKER_DEVIATES} ({RULE_INSTRUCTION_LOG}); {RULE_LIMIT_CAP}; {RULE_BANK_SETTLES}"
    else:
        rule = f"{RULE_USER_MATCHES}; {RULE_BANK_SETTLES}"
    return Award(
        checkout_id=checkout_id or ("checkout-" + instruction.instruction_id),
        instruction_id=instruction.instruction_id,
        party=party,
        amount=purchase.amount,
        user_pays=purchase.amount if party == USER else ZERO,
        maker_pays=purchase.amount if party == MAKER else ZERO,
        bank_pays=ZERO,
        cause=cause,
        rule=rule,
        cap=instruction.limit,
        deviations=deviations,
    )


def explain(award: Award) -> str:
    """One plain sentence for a receipt, a log line or a CLI answer."""
    if award.party == MAKER:
        return (
            f"The maker refunds {award.maker_pays} of the {award.amount} charged "
            f"({award.cause}), inside the user's cap of {award.cap}. "
            f"The bank reverses the charge and absorbs nothing. Sources: {RULE_MAKER_DEVIATES}; {RULE_LIMIT_CAP}."
        )
    if award.cause == "approved_after_the_fact":
        return (
            f"The user approved the {award.amount} deviation after the fact, so the user pays. "
            f"Source: {RULE_USER_MATCHES}."
        )
    return (
        f"The {award.amount} charge matches the logged instruction, so the user pays (their own choice). "
        f"Source: {RULE_USER_MATCHES}."
    )


class LiabilityBook:
    """A ledger with one settlement per instruction, safe under concurrent checkouts.

    `agents` maps an agent id to the one user it is allowed to act for. Recording an
    instruction and settling a checkout take the same lock, so two simultaneous checkouts
    on one instruction cannot both succeed: the second is refused as DuplicateCheckout and
    nothing is charged twice (zero double-spend).
    """

    def __init__(self, agents: Mapping[str, str]):
        if agents is None or (isinstance(agents, Mapping) and not agents):
            raise EmptyInstruction("agents must map at least one agent id to its user", "agents")
        if not isinstance(agents, Mapping):
            raise MalformedInstruction("agents must be an object", "agents")
        self._agents = {_text(agent, "agent"): _text(user, "user") for agent, user in agents.items()}
        self._lock = threading.RLock()
        self._instructions: dict = {}
        self._awards: dict = {}
        self._totals = {USER: ZERO, MAKER: ZERO, BANK: ZERO}

    @property
    def agents(self) -> dict:
        return dict(self._agents)

    def record(self, request, *, agent: Optional[str] = None) -> Instruction:
        instruction = request if isinstance(request, Instruction) else Instruction.from_mapping(request, agent=agent)
        with self._lock:
            owner = self._agents.get(instruction.agent)
            if owner is None:
                raise UnauthorisedCaller(f"agent '{instruction.agent}' is not registered for any user", "agent")
            if owner != instruction.user:
                raise UnauthorisedCaller(f"agent '{instruction.agent}' may not act for '{instruction.user}'", "user")
            if instruction.instruction_id in self._instructions:
                raise MalformedInstruction(f"instruction '{instruction.instruction_id}' was already recorded", "instruction_id")
            self._instructions[instruction.instruction_id] = instruction
        return instruction

    def checkout(self, request, *, actor: Optional[str] = None, checkout_id: Optional[str] = None) -> Award:
        purchase = request if isinstance(request, Purchase) else Purchase.from_mapping(request)
        with self._lock:
            instruction = self._instructions.get(purchase.instruction_id)
            if instruction is None:
                raise UnknownInstruction(
                    f"no instruction recorded as '{purchase.instruction_id}': record it before checkout",
                    "instruction_id",
                )
            if not isinstance(actor, str) or not actor.strip():
                raise UnauthorisedCaller("an actor id is required to settle a checkout", "actor")
            if actor.strip() != instruction.agent:
                raise UnauthorisedCaller(
                    f"actor '{actor.strip()}' is not the agent that recorded '{instruction.instruction_id}'", "actor")
            if purchase.user != instruction.user:
                raise UnauthorisedCaller(
                    f"the checkout is for '{purchase.user}', not the user that recorded '{instruction.instruction_id}'",
                    "user",
                )
            settled = self._awards.get(instruction.instruction_id)
            if settled is not None:
                raise DuplicateCheckout(
                    f"instruction '{instruction.instruction_id}' is already settled: settling it again would double-spend",
                    "instruction_id", settled,
                )
            award = decide(instruction, purchase, checkout_id=checkout_id)
            self._awards[instruction.instruction_id] = award
            self._totals[USER] += award.user_pays
            self._totals[MAKER] += award.maker_pays
            self._totals[BANK] += award.bank_pays
            return award

    def settlement(self, instruction_id: str) -> Optional[Award]:
        return self._awards.get(instruction_id)

    def totals(self) -> dict:
        return dict(self._totals)

    def instruction_count(self) -> int:
        return len(self._instructions)

    def settled_count(self) -> int:
        return len(self._awards)


def adjudicate_request(payload: Mapping) -> dict:
    """One-shot, stateless entry point: record one instruction, then settle one checkout.

    Returns {"award": ..., "explain": ..., "book": {...}} on success, or a typed error
    dict from LiabilityError.as_dict() so callers can branch on `error`.
    """
    try:
        if payload is None:
            raise EmptyInstruction("request is required", "request")
        if not isinstance(payload, Mapping):
            raise MalformedInstruction("request must be an object", "request")
        book = LiabilityBook(payload.get("agents"))
        agent = payload.get("agent")
        instruction = book.record(payload.get("instruction"), agent=agent)
        award = book.checkout(payload.get("checkout"), actor=payload.get("actor") or agent)
        return {
            "award": award.as_dict(),
            "explain": explain(award),
            "instruction": instruction.instruction_id,
            "book": {"totals": {party: str(amount) for party, amount in book.totals().items()}},
        }
    except LiabilityError as error:
        return error.as_dict()
