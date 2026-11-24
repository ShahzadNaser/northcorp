# Copyright (c) 2026, Shahzad Naser and contributors
# For license information, please see license.txt

# UAE VAT 201 Northcorp - the standard ERPNext "UAE VAT 201" report, with the input VAT
# from submitted Expense Claims added to Box 9 (Standard Rated Expenses).
# The standard report only reads Purchase Invoices for Box 9, so VAT claimed through
# Expense Claims was missing from the return.
#
# Expense Claims record VAT as a fixed amount and mix VAT and non-VAT lines, so the
# taxable amount added to Box 9 is VAT / 5% rather than the claim total.

import frappe
from frappe import _
from frappe.utils import flt, fmt_money

from erpnext.regional.report.uae_vat_201.uae_vat_201 import execute as uae_vat_201_execute

STANDARD_VAT_RATE = 5.0
BOX_9 = "9"


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	columns, data = uae_vat_201_execute(filters)[:2]

	ec_vat = get_expense_claim_vat(filters)
	if not ec_vat:
		return columns, data

	ec_taxable = flt(ec_vat * 100 / STANDARD_VAT_RATE, 2)
	for row in data:
		if row and str(row.get("no")) == BOX_9:
			row["amount"] = add_amount(row.get("amount"), ec_taxable)
			row["vat_amount"] = add_amount(row.get("vat_amount"), ec_vat)
			row["legend"] = _("Standard Rated Expenses (incl. Expense Claims)")
			break

	message = _("Box 9 includes {0} VAT on {1} taxable amount from submitted Expense Claims.").format(
		fmt_money(ec_vat, precision=2), fmt_money(ec_taxable, precision=2)
	)
	return columns, data, message


def add_amount(value, extra: float):
	"""Add to a Box 9 value, keeping its type: some ERPNext versions return the amounts
	already formatted as text ("1,792,520.43"), newer ones return plain numbers."""
	total = flt(str(value or 0).replace(",", "")) + extra
	return fmt_money(total, precision=2) if isinstance(value, str) else flt(total, 2)


def get_expense_claim_vat(filters) -> float:
	"""Input VAT on submitted Expense Claims in the period, from their VAT tax rows
	(Tax accounts named VAT, excluding reverse charge)."""
	conditions = ["ec.docstatus = 1", "a.account_type = 'Tax'", "a.name like %(vat)s", "a.name not like %(rcm)s"]
	values = {"vat": "%VAT%", "rcm": "%RCM%"}

	if filters.get("company"):
		conditions.append("ec.company = %(company)s")
		values["company"] = filters.company
	if filters.get("from_date"):
		conditions.append("ec.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("ec.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	result = frappe.db.sql(
		f"""
		select coalesce(sum(t.base_tax_amount), 0)
		from `tabExpense Taxes and Charges` t
		inner join `tabExpense Claim` ec on ec.name = t.parent and t.parenttype = 'Expense Claim'
		inner join `tabAccount` a on a.name = t.account_head
		where {" and ".join(conditions)}
		""",
		values,
	)
	return flt(result[0][0], 2) if result else 0.0
