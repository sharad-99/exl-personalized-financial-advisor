"""Transaction classification: duplicates, transfers, refunds and reversals."""

from datetime import date

from app.services.spending_categorization import categorize, classify_transactions, normalize_merchant
from tests.factories import CARD, DEPOSIT, SAVINGS, account, txn


def by_flow(results):  # type: ignore[no-untyped-def]
    return {r.txn.id: (r.flow, r.exclusion_reason) for r in results}


def test_income_expense_and_refund_flows() -> None:
    rows = [
        txn(date(2026, 9, 1), "50000.00", "credit", "salary", "salary", txn_id="sal"),
        txn(date(2026, 9, 5), "2000.00", "debit", "purchase", "shopping", txn_id="buy"),
        txn(date(2026, 9, 9), "500.00", "credit", "refund", "shopping", txn_id="ref"),
    ]
    flows = by_flow(classify_transactions(rows))
    assert flows == {"sal": ("income", None), "buy": ("expense", None), "ref": ("refund", None)}


def test_duplicate_import_is_excluded_once() -> None:
    original = txn(date(2026, 9, 5), "799.00", "debit", "purchase", "dining", description="UPI/CAFE/123", txn_id="a")
    duplicate = txn(date(2026, 9, 5), "799.00", "debit", "purchase", "dining", description="UPI/CAFE/123", txn_id="b")
    flows = by_flow(classify_transactions([duplicate, original]))
    excluded = [k for k, v in flows.items() if v == ("excluded", "probable_duplicate")]
    assert len(excluded) == 1
    assert sorted(v[0] for v in flows.values()) == ["excluded", "expense"]


def test_same_amount_different_description_is_not_a_duplicate() -> None:
    a = txn(date(2026, 9, 5), "100.00", "debit", "purchase", "dining", description="UPI/CAFE/1")
    b = txn(date(2026, 9, 5), "100.00", "debit", "purchase", "dining", description="UPI/CAFE/2")
    assert all(r.flow == "expense" for r in classify_transactions([a, b]))


def test_reversal_neutralises_both_legs() -> None:
    original = txn(date(2026, 9, 5), "1500.00", "debit", "purchase", "shopping", txn_id="orig")
    reversal = txn(date(2026, 9, 5), "1500.00", "credit", "reversal", "shopping", reverses="orig", txn_id="rev")
    flows = by_flow(classify_transactions([original, reversal]))
    assert flows == {"orig": ("excluded", "reversed"), "rev": ("excluded", "reversal")}


def test_orphan_reversal_is_flagged() -> None:
    reversal = txn(date(2026, 9, 5), "1500.00", "credit", "reversal", "shopping", reverses="missing", txn_id="rev")
    assert by_flow(classify_transactions([reversal])) == {"rev": ("excluded", "orphan_reversal")}


def test_card_bill_payment_is_an_internal_transfer_not_an_expense() -> None:
    rows = [
        txn(date(2026, 9, 2), "3000.00", "debit", "purchase", "dining", account=CARD, txn_id="card-buy"),
        txn(date(2026, 9, 18), "3000.00", "debit", "transfer_out", "transfer", group="g1", txn_id="out"),
        txn(date(2026, 9, 18), "3000.00", "credit", "transfer_in", "transfer", account=CARD, group="g1", txn_id="in"),
    ]
    flows = by_flow(classify_transactions(rows, [account(), account(CARD, "credit_card")]))
    assert flows["card-buy"] == ("expense", None)
    assert flows["out"] == ("excluded", "internal_transfer")
    assert flows["in"] == ("excluded", "internal_transfer")


def test_unbalanced_or_one_legged_transfer_is_unmatched() -> None:
    rows = [txn(date(2026, 9, 2), "500.00", "debit", "transfer_out", "transfer", group="lonely", txn_id="out")]
    assert by_flow(classify_transactions(rows)) == {"out": ("excluded", "unmatched_transfer")}


def test_transfer_into_deposit_is_marked_as_savings() -> None:
    rows = [
        txn(date(2026, 9, 27), "5000.00", "debit", "transfer_out", "transfer", group="s", txn_id="out"),
        txn(date(2026, 9, 27), "5000.00", "credit", "transfer_in", "transfer", account=DEPOSIT, group="s", txn_id="in"),
    ]
    results = {r.txn.id: r for r in classify_transactions(rows, [account(SAVINGS), account(DEPOSIT, "fixed_deposit")])}
    assert results["in"].is_savings_transfer
    assert not results["out"].is_savings_transfer


def test_keyword_rules_recover_uncategorised_transactions() -> None:
    groceries = txn(date(2026, 9, 2), "800.00", "debit", "purchase", "uncategorized", description="UPI/FRESH MART/1")
    unknown = txn(date(2026, 9, 2), "800.00", "debit", "purchase", "uncategorized", description="POS/MISC VENDOR/9")
    assert categorize(groceries) == ("groceries", "keyword_rule")
    assert categorize(unknown) == ("uncategorized", "fallback")


def test_classification_is_order_independent() -> None:
    rows = [
        txn(date(2026, 9, 5), "799.00", "debit", "purchase", "dining", description="UPI/CAFE/1", txn_id="x"),
        txn(date(2026, 9, 5), "799.00", "debit", "purchase", "dining", description="UPI/CAFE/1", txn_id="y"),
    ]
    assert by_flow(classify_transactions(rows)) == by_flow(classify_transactions(list(reversed(rows))))


def test_normalize_merchant_strips_reference_tokens() -> None:
    assert normalize_merchant(None, "UPI/FRESHMART GROCERS/839201") == "UPI"
    assert normalize_merchant("Cafe Aroma #12", "x") == "CAFE AROMA"
