
from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import getdate,flt
from hrms.hr.doctype.expense_claim.expense_claim import ExpenseClaim
from erpnext.accounts.general_ledger import make_gl_entries


class CustomExpenseClaim(ExpenseClaim):
    @frappe.whitelist()
    def calculate_taxes(self):
        self.total_taxes_and_charges = 0
        for tax in self.taxes:
            self.round_floats_in(tax)

            if tax.rate:
                tax.tax_amount = flt(
                    flt(self.total_sanctioned_amount) * flt(flt(tax.rate) / 100),
                    tax.precision("tax_amount"),
                )

            tax.total = flt(tax.tax_amount) + flt(self.total_sanctioned_amount)
            self.total_taxes_and_charges += flt(tax.tax_amount)
            self.set_base_fields_amount(tax, ["tax_amount", "total"])

        self.round_floats_in(self, ["total_taxes_and_charges"])

        party_claims = flt(0)
        for row in self.expense_claim_party_details:
            party_claims += flt(row.get("amount"))

        self.grand_total = (
            flt(self.total_sanctioned_amount)
            + flt(self.total_taxes_and_charges)
            + flt(party_claims)
            - flt(self.total_advance_amount)
        )
        self.round_floats_in(self, ["grand_total"])
        self.set_base_fields_amount(self, ["grand_total"])

    def make_gl_entries(self, cancel=False):
        if flt(self.total_sanctioned_amount) > 0:
            gl_entries = self.get_gl_entries()
            # expense expense_claim_party_details
            for row in self.expense_claim_party_details:
                if row.get("party_type") == 'Employee':
                    account = 'Employee Advances - NRC' if self.company == 'NORTHCORP LLC' else 'Employee Advances - NRI'
                elif row.get("party_type") == 'Supplier':
                    account = 'Creditors - NRC' if self.company == 'NORTHCORP LLC' else 'Creditors - NRI'
                else:
                    account = self.payable_account
                t_key = "debit"
                tac_key = "debit_in_account_currency"
                ttc_key = "debit_in_transaction_currency"
                if flt(row.get("amount")) < flt(0):

                    t_key = "credit"
                    tac_key = "credit_in_account_currency"
                    ttc_key = "credit_in_transaction_currency"

                gl_entries.append(
                    self.get_gl_dict(
                        {
                            "account": account,
                            t_key: flt(row.get("amount")),
                            tac_key: flt(row.get("amount")),
                            ttc_key: flt(row.get("amount")),
                            "against": self.employee,
                            "party_type": row.get("party_type"),
                            "party": row.get("party"),
                            "against_voucher_type": self.doctype,
                            "against_voucher": self.name,
                            "cost_center": row.get("cost_center") or self.cost_center,
                            "project": row.get("project") or self.project,
                            "transaction_exchange_rate": self.exchange_rate,
                            "remarks": row.get("description"),
                        },
                        account_currency=self.currency,
                        item=row,
                    )
                )

            make_gl_entries(gl_entries, cancel)
