# Copyright (c) 2026, Shahzad Naser and contributors
# For license information, please see license.txt

# UAE VAT 201 Northcorp - the standard ERPNext "UAE VAT 201" report with Box 9
# (Standard Rated Expenses) completed so it matches the input VAT in the ledger.
# The standard report only reads the "Recoverable Standard Rated Expenses" field on
# Purchase Invoices, so Box 9 was missing:
#   - input VAT on submitted Expense Claims,
#   - input VAT posted by Journal Entries,
#   - debit notes (Purchase Invoice returns) on versions that only count positive values.
#
# Expense Claims and Journal Entries carry VAT as a fixed amount (claims mix VAT and
# non-VAT lines), so the taxable amount added for them, and for debit notes, is VAT / 5%.

import frappe
from frappe import _
from frappe.utils import flt, fmt_money

from erpnext.regional.report.uae_vat_201.uae_vat_201 import execute as uae_vat_201_execute

STANDARD_VAT_RATE = 5.0
BOX_9 = "9"
# Input VAT accounts, e.g. "VAT 5% Purchase - NRC" (reverse charge accounts are excluded)
INPUT_VAT_ACCOUNT = "%VAT%Purchase%"
REVERSE_CHARGE_ACCOUNT = "%RCM%"


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	columns, data = uae_vat_201_execute(filters)[:2]

	box9 = next((row for row in data if row and str(row.get("no")) == BOX_9), None)
	if not box9:
		return columns, data

	additions = []  # (label, vat)
	debit_note_vat = get_missing_debit_note_vat(filters, to_number(box9.get("vat_amount")))
	if debit_note_vat:
		additions.append((_("Debit Notes"), debit_note_vat))
	ec_vat = get_expense_claim_vat(filters)
	if ec_vat:
		additions.append((_("Expense Claims"), ec_vat))
	je_vat = get_journal_entry_vat(filters)
	if je_vat:
		additions.append((_("Journal Entries"), je_vat))

	if not additions:
		return columns, data

	total_vat = sum(vat for _label, vat in additions)
	total_taxable = sum(taxable_amount(vat) for _label, vat in additions)
	box9["amount"] = add_amount(box9.get("amount"), total_taxable)
	box9["vat_amount"] = add_amount(box9.get("vat_amount"), total_vat)
	box9["legend"] = _("Standard Rated Expenses (incl. {0})").format(", ".join(label for label, _vat in additions))

	message = _("Box 9 includes: {0}.").format(
		"; ".join(
			_("{0} VAT {1} on {2}").format(label, fmt_money(vat, precision=2), fmt_money(taxable_amount(vat), precision=2))
			for label, vat in additions
		)
	)
	return columns, data, message


def taxable_amount(vat: float) -> float:
	return flt(vat * 100 / STANDARD_VAT_RATE, 2)


def to_number(value) -> float:
	# some ERPNext versions return the amounts already formatted as text ("1,792,520.43")
	return flt(str(value or 0).replace(",", ""))


def add_amount(value, extra: float):
	"""Add to a Box 9 value, keeping its type (formatted text or number)."""
	total = to_number(value) + extra
	return fmt_money(total, precision=2) if isinstance(value, str) else flt(total, 2)


def get_conditions(filters, alias: str, values: dict) -> list[str]:
	conditions = []
	if filters.get("company"):
		conditions.append(f"{alias}.company = %(company)s")
		values["company"] = filters.company
	if filters.get("from_date"):
		conditions.append(f"{alias}.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append(f"{alias}.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date
	return conditions


def get_missing_debit_note_vat(filters, standard_box9_vat: float) -> float:
	"""VAT on debit notes, when the standard report left them out. Some ERPNext versions
	only sum positive "Recoverable Standard Rated Expenses", so returns are skipped;
	newer versions include them, in which case nothing is added."""
	values = {}
	conditions = ["pi.docstatus = 1", *get_conditions(filters, "pi", values)]
	result = frappe.db.sql(
		f"""
		select
			coalesce(sum(case when pi.recoverable_standard_rated_expenses > 0
				then pi.recoverable_standard_rated_expenses else 0 end), 0),
			coalesce(sum(case when pi.recoverable_standard_rated_expenses < 0
				then pi.recoverable_standard_rated_expenses else 0 end), 0)
		from `tabPurchase Invoice` pi
		where {" and ".join(conditions)}
		""",
		values,
	)
	positive, negative = (flt(result[0][0], 2), flt(result[0][1], 2)) if result else (0.0, 0.0)
	if negative and abs(standard_box9_vat - positive) < 0.01:
		return negative
	return 0.0


def get_expense_claim_vat(filters) -> float:
	"""Input VAT on submitted Expense Claims, from their VAT tax rows."""
	values = {"input_vat": INPUT_VAT_ACCOUNT, "rcm": REVERSE_CHARGE_ACCOUNT}
	conditions = [
		"ec.docstatus = 1",
		"t.account_head like %(input_vat)s",
		"t.account_head not like %(rcm)s",
		*get_conditions(filters, "ec", values),
	]
	result = frappe.db.sql(
		f"""
		select coalesce(sum(t.base_tax_amount), 0)
		from `tabExpense Taxes and Charges` t
		inner join `tabExpense Claim` ec on ec.name = t.parent and t.parenttype = 'Expense Claim'
		where {" and ".join(conditions)}
		""",
		values,
	)
	return flt(result[0][0], 2) if result else 0.0


def get_journal_entry_vat(filters) -> float:
	"""Net input VAT posted by Journal Entries to the input VAT accounts."""
	values = {"input_vat": INPUT_VAT_ACCOUNT, "rcm": REVERSE_CHARGE_ACCOUNT}
	conditions = [
		"gle.is_cancelled = 0",
		"gle.voucher_type = 'Journal Entry'",
		"gle.account like %(input_vat)s",
		"gle.account not like %(rcm)s",
		*get_conditions(filters, "gle", values),
	]
	result = frappe.db.sql(
		f"""
		select coalesce(sum(gle.debit - gle.credit), 0)
		from `tabGL Entry` gle
		where {" and ".join(conditions)}
		""",
		values,
	)
	return flt(result[0][0], 2) if result else 0.0
