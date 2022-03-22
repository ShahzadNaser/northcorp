# Copyright (c) 2021, The Nexperts Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import getdate, flt
import erpnext
from frappe import _
from erpnext.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry

class CustomPayrollEntry(PayrollEntry):
    def make_accrual_jv_entry(self):
        from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions
        self.check_permission("write")
        # earnings = get_project_wise_breakdown(component_type = "earnings") or {}
        # deductions = self.get_salary_component_total(component_type = "deductions") or {}

        earnings = get_project_wise_breakdown(self.name) or []

        payroll_payable_account = self.payroll_payable_account
        jv_name = ""
        precision = frappe.get_precision("Journal Entry Account", "debit_in_account_currency")

        if earnings:
            journal_entry = frappe.new_doc("Journal Entry")
            journal_entry.voucher_type = "Journal Entry"
            journal_entry.user_remark = _("Accrual Journal Entry for salaries from {0} to {1}")\
                .format(self.start_date, self.end_date)
            journal_entry.company = self.company
            journal_entry.posting_date = self.posting_date
            accounting_dimensions = get_accounting_dimensions() or []

            accounts = []
            currencies = []
            payable_amount = 0
            multi_currency = 0
            company_currency = erpnext.get_company_currency(self.company)

            # Earnings
            for row in earnings:
                if row.amount > 0:
                    exchange_rate, amt = self.get_amount_and_exchange_rate_for_journal_entry(row.default_payroll_account, row.amount, company_currency, currencies)
                    payable_amount += flt(row.amount, precision)
                    accounts.append(self.update_accounting_dimensions({
                        "account": row.default_payroll_account,
                        "debit_in_account_currency": flt(amt, precision),
                        "exchange_rate": flt(exchange_rate),
                        "cost_center": row.payroll_cost_center or self.cost_center,
                        "project": row.project,
                        "reference_type":"Payroll Entry",
                        "reference_name":self.name
                    }, accounting_dimensions))

            # Deductions
            # for acc_cc, amount in deductions.items():
            #     exchange_rate, amt = self.get_amount_and_exchange_rate_for_journal_entry(acc_cc[0], amount, company_currency, currencies)
            #     payable_amount -= flt(amount, precision)
            #     accounts.append(self.update_accounting_dimensions({
            #         "account": acc_cc[0],
            #         "credit_in_account_currency": flt(amt, precision),
            #         "exchange_rate": flt(exchange_rate),
            #         "cost_center": acc_cc[1] or self.cost_center,
            #         "project": self.project
            #     }, accounting_dimensions))

            # Payable amount
            exchange_rate, payable_amt = self.get_amount_and_exchange_rate_for_journal_entry(payroll_payable_account, payable_amount, company_currency, currencies)
            accounts.append(self.update_accounting_dimensions({
                "account": payroll_payable_account,
                "credit_in_account_currency": flt(payable_amt, precision),
                "exchange_rate": flt(exchange_rate),
                "cost_center": self.cost_center,
                "reference_type":"Payroll Entry",
                "reference_name":self.name
            }, accounting_dimensions))

            journal_entry.set("accounts", accounts)
            if len(currencies) > 1:
                multi_currency = 1
            journal_entry.multi_currency = multi_currency
            journal_entry.title = payroll_payable_account
            journal_entry.save()

            try:
                journal_entry.submit()
                jv_name = journal_entry.name
                self.update_salary_slip_status(jv_name = jv_name)
            except Exception as e:
                if type(e) in (str, list, tuple):
                    frappe.msgprint(e)
                raise

        return jv_name

def get_project_wise_breakdown(pe=None):
    result = []
    if not pe:
        return result

    return frappe.db.sql("""
        SELECT 
            ss.department,
            dep.payroll_cost_center,
            al.project,
            dep.default_payroll_account,
            SUM(al.amount) AS amount
        FROM
            `tabSalary Slip` ss
                LEFT JOIN
            `tabProject Allocation` al ON al.parent = ss.name
                LEFT JOIN
            `tabDepartment` dep ON ss.department = dep.name
        WHERE
            ss.payroll_entry = %s
        GROUP BY ss.department, al.project
    """,(pe),as_dict=True,debug=True)           