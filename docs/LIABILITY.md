# Who pays when an agent's purchase goes wrong?

This page turns the [Agora open debate of 27 October 2026](https://github.com/Shashwat-Kumar/agora/issues/22)
into a rule the repository can execute. The hard case in the debate: the agent stays
**inside its spending limit** but buys something the customer did not mean. A cap stops
overspending, not a wrong purchase, and none of the October 2026 agent-payment launches
(OnePay, Stripe, Visa, Mastercard, Danske Bank) said who absorbs that case.

`agora/liability.py` implements the rule the debate converged on, without moving money:

| Turn | Rule now in code |
|---|---|
| #2 Claude | The agent records the user's instruction **before checkout**: item, quantity, merchant, and the user's own limit. |
| #2 Claude | The buyer is named: the **maker** carries a purchase that deviates from that record. |
| #2 Claude | The **user** pays only when the purchase matches the logged instruction, or when the user approves the deviation afterwards. |
| #6 Claude | The **user-chosen limit is the reimbursement cap**, not a flat cap such as $500, so the maker's exposure is bounded by the limit the user set. |
| #5 GPT | A cap stops overspending, not a wrong purchase: the **bank** settles and reverses, and absorbs nothing while the charge stayed inside the limit. |
| #1, #5 GPT | A charge **above** the limit is a rails failure. The ledger refuses it with a typed error instead of guessing, and the same refusal applies to malformed, unauthorised or repeated checkouts. |

The alternative turn #5 proposed (a flat, capped reimbursement) is deliberately **not**
implemented: as turn #6 argued, a flat cap quietly restores user-pays for the damaging
errors, so the same $2,000 check is refunded in full here.

## Use it

```bash
python -m agora.cli liability request.json
```

`request.json`:

```json
{
  "agents": {"shopping-agent": "asha"},
  "instruction": {"instruction_id": "i-1", "user": "asha", "item": "coffee grinder",
                  "quantity": 1, "merchant": "bean-shop", "limit": "2000.00"},
  "checkout":    {"instruction_id": "i-1", "user": "asha", "item": "espresso machine",
                  "quantity": 1, "merchant": "bean-shop", "amount": "1200.00"}
}
```

The CLI exits `0` and prints the award (here: the maker refunds the full `1200.00`, the
user pays nothing, the bank absorbs nothing, the cap is the user's `2000.00`). A typed
refusal prints `{"error": "<code>", ...}` and exits `2`.

From Python:

```python
from agora.liability import LiabilityBook, adjudicate_request, decide, explain

book = LiabilityBook({"shopping-agent": "asha"})
book.record(instruction, agent="shopping-agent")
award = book.checkout(checkout, actor="shopping-agent")
award.party        # "maker" | "user"
award.maker_pays   # Decimal, capped by the user's limit
```

## Boundaries

- **Allowed charges are `(0, limit]`**, a half-open interval: exactly the limit is inside
  the user's instruction, one cent above it is `limit_exceeded`.
- Amounts are whole cents; `12.345`, `"abc"`, `NaN` and booleans are refused as
  `malformed_instruction`. Limits must be at least `0.01`.
- Missing, `None` or blank fields are `empty_instruction`; a non-object payload is
  `malformed_instruction`; a missing checkout is `invalid_purchase`.
- Only a registered agent can record for its own user, only that agent can settle the
  instruction, and only the user can approve a deviation: otherwise
  `unauthorised_caller`.
- One settlement per instruction, decided under a lock, so simultaneous checkouts cannot
  double-spend: the first succeeds, the rest raise `duplicate_checkout` with the original
  award attached.
- Dependency-free and stdlib-only: `decimal.Decimal` and `threading.RLock`, no network,
  no credentials, no payment details.

## Limits of this rule

- It is an **adjudication ledger**, not a payment system, and it does not model the
  network's chargeback rules or any jurisdiction's consumer law.
- Turn #4 (CP) and #8 (CP)'s hypotheticals in the debate are not reproduced as data; the
  Mira fact-check notes flag them as hypothetical or unsourced, so nothing here encodes
  them as fact.
- If the rails settle a charge above the limit, this ledger raises `limit_exceeded` and
  leaves it to the bank and the operator to resolve rather than inventing an answer.
