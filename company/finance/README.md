# Company OS finance

The deterministic financial evidence layer. It records money and computes over
what was recorded — it does not forecast, does not estimate, and does not spend.

Company OS could already track task usage, research usage, workforce
capabilities and organizational recommendations. It could not answer what a
video cost, what it earned, or whether a reusable tool has paid for itself. That
is what this package is for.

## The four rules everything else follows from

1. **Unknown stays unknown.** Every figure is a number, or `None` with a reason
   in a `missing` tuple. A gap never becomes a zero — a zero cost reads as free,
   and a zero budget consumption reads as untouched.
2. **Money is `Decimal` and carries its currency.** A `float` is refused at
   construction. Two currencies are never combined, because converting them
   needs a dated exchange-rate observation nobody has supplied.
3. **Evidence or no record.** A cost, revenue line, price, budget and investment
   all refuse to exist without a pointer to something a second person can check.
4. **Append-only.** A correction is a new record that supersedes an old one, so
   what the company believed in March is still readable in September.

## Layout

| Module | What it holds |
| --- | --- |
| `money.py` | `Money`: exact Decimal arithmetic, currency-bound, exact `split` |
| `period.py` | `FinancialPeriod`: the accounting window and its reporting currency |
| `common.py` | `SubjectRef` and the validators every record shares |
| `costs.py` | `CostRecord`, `CostAdjustment`, allocation |
| `revenue.py` | `RevenueRecord` and the rules that keep it ours |
| `rates.py` | `CostRate`, `RateCard`: dated prices, never overwritten |
| `labour.py` | `LabourRate`: an hour's cost, only when somebody supplied it |
| `mapping.py` | `ResourceCostMapping`: measured usage × a supplied rate |
| `budget.py` | `BudgetLine`, `consumption()` |
| `economics.py` | deliverable, format, profitability, AI and research efficiency |
| `investment.py` | `ReusableInvestment`, `ReuseEvent`, break-even |
| `proposals.py` | `SpendProposal`, `SpendDecision`, the CEO-reserved gate |
| `recommendations.py` | advisory recommendations, with handoff to org intelligence |
| `integrity.py` | the cross-record checks |
| `store.py` | append-only file-backed state under a caller-supplied directory |

## Three things it deliberately cannot do

**Infer revenue.** A public view count times a plausible RPM produces a number
that looks real and is wrong by an unknown factor. `RevenueRecord` refuses
public, estimated and competitor evidence kinds, `EvidenceOrigin` has no member
for a third-party figure, and `SubjectKind` has no `COMPETITOR` member, so
somebody else's video cannot be named as a revenue subject in the first place.

**Price usage without a rate.** `mapping.price()` returns `Money | None`. No
provider price is hardcoded anywhere in this package — a test walks the AST to
make sure. An unpriced provider comes back as unknown with a reason, never as
free.

**Spend.** There is no `pay`, `subscribe`, `execute` or `approve` anywhere here,
and tests assert their absence by name. `permissions.yaml` reserves
`large_or_recurring_paid_api_spend` to the CEO; `reserved_actions_for_spend`
reads that file rather than deciding, and fails closed when it cannot.
`SpendProposal` can only be constructed as `PROPOSED`, and moving it requires a
`SpendDecision` naming a person who is not an automatic marker.

## What it consumes, and does not recount

`ai_platform.usage.ResourceUsageRecord` and the research subsystem's
`ResearchResourceRecord` already count tokens, tool calls and minutes.
Constitution rule 15 stores a canonical fact once, so `mapping.py` reads those
records rather than recounting — and reads them *duck-typed*, naming every
attribute it touches, so the boundary stays one-way and an upstream rename
raises rather than silently yielding nothing.

That one-way boundary is also what makes the capsule graph work.
`company/finance` imports no other Company OS subsystem, so
`company-organizational-intelligence` can depend on `company-finance` (it may
consume financial evidence when judging organizational efficiency) without a
cycle, and the control plane reaches finance transitively while keeping its own
eight direct dependencies.

## No single number

There is no `profit_score`, `format_score`, `employee_roi` or
`company_financial_health`. Section 23 of the brief and constitution rule 3: the
company's objective is long-term profitable audience growth, which is not one
number, and a single number would be optimised instead of it. A test scans every
dataclass in the package for a field that reads like an aggregate verdict.

The same reasoning is why `compare_formats` returns no winner. It reports both
summaries, both sample sizes, and the reasons a comparison would be unsound.

## State lives outside the repository

`FinanceStore` takes an explicit `state_dir` and never defaults to a path inside
the repository — the same choice `company/runtime/usage_store.py` made, for the
same reason: a store with a default location writes somewhere by accident. Tests
use `tmp_path`.

## Tests

```
pytest tests/test_company_finance.py
```
