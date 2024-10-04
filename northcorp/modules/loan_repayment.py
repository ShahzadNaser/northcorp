
from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import getdate
from erpnext.loan_management.doctype.loan_repayment.loan_repayment import LoanRepayment

class CustomLoanRepayment(LoanRepayment):
    def make_gl_entries(self, cancel=0, adv_adj=0):
        from erpnext.accounts.general_ledger import make_gl_entries
        gle_map = []
        loan_details = frappe.get_doc("Loan", self.against_loan)

        if self.shortfall_amount and self.amount_paid > self.shortfall_amount:
            remarks = _("Shortfall Repayment of {0}.\nRepayment against Loan: {1}").format(self.shortfall_amount,
                self.against_loan)
        elif self.shortfall_amount:
            remarks = _("Shortfall Repayment of {0}").format(self.shortfall_amount)
        else:
            remarks = _("Repayment against Loan: ") + self.against_loan

        if not loan_details.repay_from_salary:
            if self.total_penalty_paid:
                gle_map.append(
                    self.get_gl_dict({
                        "account": loan_details.loan_account,
                        "against": loan_details.payment_account,
                        "debit": self.total_penalty_paid,
                        "debit_in_account_currency": self.total_penalty_paid,
                        "against_voucher_type": "Loan",
                        "against_voucher": self.against_loan,
                        "remarks": _("Penalty against loan:") + self.against_loan,
                        "cost_center": self.cost_center,
                        "party_type": self.applicant_type,
                        "party": self.applicant,
                        "posting_date": getdate(self.posting_date)
                    })
                )

                gle_map.append(
                    self.get_gl_dict({
                        "account": loan_details.penalty_income_account,
                        "against": loan_details.payment_account,
                        "credit": self.total_penalty_paid,
                        "credit_in_account_currency": self.total_penalty_paid,
                        "against_voucher_type": "Loan",
                        "against_voucher": self.against_loan,
                        "remarks": _("Penalty against loan:") + self.against_loan,
                        "cost_center": self.cost_center,
                        "posting_date": getdate(self.posting_date)
                    })
                )

            gle_map.append(
                self.get_gl_dict({
                    "account": loan_details.payment_account,
                    "against": loan_details.loan_account + ", " + loan_details.interest_income_account
                            + ", " + loan_details.penalty_income_account,
                    "debit": self.amount_paid,
                    "debit_in_account_currency": self.amount_paid,
                    "against_voucher_type": "Loan",
                    "against_voucher": self.against_loan,
                    "remarks": remarks,
                    "cost_center": self.cost_center,
                    "posting_date": getdate(self.posting_date)
                })
            )

            gle_map.append(
                self.get_gl_dict({
                    "account": loan_details.loan_account,
                    "party_type": loan_details.applicant_type,
                    "party": loan_details.applicant,
                    "against": loan_details.payment_account,
                    "credit": self.amount_paid,
                    "credit_in_account_currency": self.amount_paid,
                    "against_voucher_type": "Loan",
                    "against_voucher": self.against_loan,
                    "remarks": remarks,
                    "cost_center": self.cost_center,
                    "posting_date": getdate(self.posting_date)
                })
            )

            if gle_map:
                make_gl_entries(gle_map, cancel=cancel, adv_adj=adv_adj, merge_entries=False)

        if loan_details.repay_from_salary and self.get("payroll_entry"):
            gle_map.append(
                self.get_gl_dict({
                    "account": frappe.db.get_value("Payroll Entry", self.get("payroll_entry"), "payroll_payable_account"),
                    "against": loan_details.loan_account + ", " + loan_details.interest_income_account
                            + ", " + loan_details.penalty_income_account,
                    "debit": self.amount_paid,
                    "debit_in_account_currency": self.amount_paid,
                    "against_voucher_type": "Loan",
                    "against_voucher": self.against_loan,
                    "remarks": remarks,
                    "cost_center": self.cost_center,
                    "posting_date": getdate(self.posting_date)
                })
            )

            gle_map.append(
                self.get_gl_dict({
                    "account": loan_details.loan_account,
                    "party_type": loan_details.applicant_type,
                    "party": loan_details.applicant,
                    "against": frappe.db.get_value("Payroll Entry", self.get("payroll_entry"), "payroll_payable_account"),
                    "credit": self.amount_paid,
                    "credit_in_account_currency": self.amount_paid,
                    "against_voucher_type": "Loan",
                    "against_voucher": self.against_loan,
                    "remarks": remarks,
                    "cost_center": self.cost_center,
                    "posting_date": getdate(self.posting_date)
                })
            )

            if gle_map:
                make_gl_entries(gle_map, cancel=cancel, adv_adj=adv_adj, merge_entries=False)
