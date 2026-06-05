import frappe
import erpnext
from frappe import _
from frappe.utils import flt
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions
from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry


class CustomPayrollEntry(PayrollEntry):

    def make_accrual_jv_entry(self, submitted_salary_slips):
        """
        Override to build accrual JV with:
        - One debit row per (account, cost_center, project) for earnings
        - One credit row per (account, cost_center, employee, salary_component) for deductions
          with party_type=Employee and party=employee on each deduction row
        - Single credit to payroll payable account for net payable
        - Rounding difference posted to 754 account (account_number = '754') if any
        Account resolution: Salary Component Account -> fallback to Department default_payroll_account
        """
        self.check_permission("write")

        earning_rows   = get_earnings_breakdown(self.name, self.company) or []
        deduction_rows = get_deductions_breakdown(self.name, self.company) or []

        if not earning_rows and not deduction_rows:
            return ""

        payroll_payable_account = self.payroll_payable_account
        precision               = frappe.get_precision("Journal Entry Account", "debit_in_account_currency")
        accounting_dimensions   = get_accounting_dimensions() or []
        company_currency        = erpnext.get_company_currency(self.company)

        accounts       = []
        currencies     = []
        payable_amount = 0
        gratuity_amount = 0

        # ------------------------------------------------------------------ #
        #  EARNINGS  –  debit per (account, cost_center, project)             #
        # ------------------------------------------------------------------ #
        for row in earning_rows:
            if not row.amount or row.amount <= 0:
                continue

            if not row.account and row.salary_component != "Gratuity":
                frappe.throw(
                    _(
                        "No account found for Salary Component {0} (company {1}) "
                        "and no Default Payroll Account set on Department {2}. "
                        "Please set either a Salary Component Account or a "
                        "Default Payroll Account on the Department."
                    ).format(
                        frappe.bold(row.salary_component),
                        frappe.bold(self.company),
                        frappe.bold(row.department),
                    )
                )

            exchange_rate, amt = self.get_amount_and_exchange_rate_for_journal_entry(
                row.account,
                row.amount,
                company_currency,
                currencies,
            )

            payable_amount += flt(row.amount, precision)

            accounts.append(
                self.update_accounting_dimensions(
                    {
                        "account"                  : row.account,
                        "debit_in_account_currency": flt(amt, precision),
                        "exchange_rate"            : flt(exchange_rate),
                        "cost_center"              : row.payroll_cost_center or self.cost_center,
                        "project"                  : row.project,
                        "reference_type"           : "Payroll Entry",
                        "reference_name"           : self.name,
                    },
                    accounting_dimensions,
                )
            )

        # ------------------------------------------------------------------ #
        #  DEDUCTIONS  –  credit per (account, cost_center, employee)         #
        #  party_type = Employee, party = employee                            #
        #  Advance Payment is a debit (increases payable)                     #
        # ------------------------------------------------------------------ #
        for row in deduction_rows:
            if not row.amount or row.amount <= 0:
                continue

            if not row.account and row.salary_component != "Gratuity":
                frappe.throw(
                    _(
                        "No account found for Salary Component {0} (company {1}) "
                        "and no Default Payroll Account set on Department {2}. "
                        "Please set either a Salary Component Account or a "
                        "Default Payroll Account on the Department."
                    ).format(
                        frappe.bold(row.salary_component),
                        frappe.bold(self.company),
                        frappe.bold(row.department),
                    )
                )

            exchange_rate, amt = self.get_amount_and_exchange_rate_for_journal_entry(
                row.account,
                row.amount,
                company_currency,
                currencies,
            )

            if row.salary_component not in ["Advance Payment","Gratuity"]:
                payable_amount -= flt(row.amount, precision)
                acc_key = "credit_in_account_currency"
            else:
                payable_amount += flt(row.amount, precision)
                acc_key = "debit_in_account_currency"
                if row.salary_component == "Gratuity":
                    row.account = frappe.db.get_value("Employee",row.employee,"gratuity_account") or "Gratuities - NRC" if self.get("company") == "NORTHCORP LLC" else "Gratuities - NRI"
            accounts.append(
                self.update_accounting_dimensions(
                    {
                        "account"      : row.account,
                        acc_key        : flt(amt, precision),
                        "exchange_rate": flt(exchange_rate),
                        "cost_center"  : row.payroll_cost_center or self.cost_center,
                        "party_type"   : "Employee",
                        "party"        : row.employee,
                        "reference_type": "Payroll Entry",
                        "reference_name": self.name,
                    },
                    accounting_dimensions,
                )
            )

        for row in frappe.db.sql(""" SELECT ss.employee,ss.gratuity_amount, dep.payroll_cost_center, emp.gratuity_account,emp.gratuity_payable_account FROM `tabSalary Slip` ss INNER JOIN `tabDepartment` dep on ss.department = dep.name LEFT JOIN `tabEmployee` emp ON ss.employee = emp.name WHERE ss.payroll_entry = '{}'""".format(self.name),as_dict=True):
            if row.get("gratuity_amount"):
                accounts.append(
                    self.update_accounting_dimensions(
                        {
                            "account"      : row.get("gratuity_account") or "Gratuities - NRC" if self.get("company") == "NORTHCORP LLC" else "Gratuities - NRI",
                            "credit_in_account_currency": flt(row.get("gratuity_amount"), precision),
                            "exchange_rate": flt(exchange_rate),
                            "cost_center"  : row.get("payroll_cost_center") or self.cost_center,
                            "party_type"   : "Employee",
                            "party"        : row.employee,
                            "reference_type": "Payroll Entry",
                            "reference_name": self.name,
                        },
                        accounting_dimensions,
                    )
                )
                accounts.append(self.update_accounting_dimensions({
                    "account"                  : row.get("gratuity_payable_account") or "715 - End of Service Indemnities - NRC" if self.get("company") == "NORTHCORP LLC" else "715 - End of Service Indemnities - NRI",
                    "debit_in_account_currency": flt(row.get("gratuity_amount"), precision),
                    "exchange_rate"            : flt(exchange_rate),
                    "cost_center"              : row.get("payroll_cost_center") or self.cost_center,
                }, accounting_dimensions)) 


        # ------------------------------------------------------------------ #
        #  GROSS PAY from salary slips — source of truth for payable amount   #
        # ------------------------------------------------------------------ #
        net_pay_total = flt(frappe.db.sql(""" SELECT sum(net_pay) from `tabSalary Slip` where payroll_entry = '{}'""".format(self.name))[0][0],precision)

        # Rounding difference = gross_pay_total - computed payable_amount
        # gross_pay_total is what should hit payroll payable
        # payable_amount is what our component-level math produced
        rounding_diff = flt(net_pay_total - payable_amount, precision)
        # ------------------------------------------------------------------ #
        #  PAYROLL PAYABLE  –  credit gross_pay_total (source of truth)       #
        # ------------------------------------------------------------------ #
        exchange_rate, payable_amt = self.get_amount_and_exchange_rate_for_journal_entry(
            payroll_payable_account,
            net_pay_total,
            company_currency,
            currencies,
        )

        accounts.append(
            self.update_accounting_dimensions(
                {
                    "account"                   : payroll_payable_account,
                    "credit_in_account_currency": flt(payable_amt, precision),
                    "exchange_rate"             : flt(exchange_rate),
                    "cost_center"               : self.cost_center,
                    "reference_type"            : "Payroll Entry",
                    "reference_name"            : self.name,
                    "party_type"                : "Supplier",
                    "party"                     : "SUP-0771",
                },
                accounting_dimensions,
            )
        )

        # ------------------------------------------------------------------ #
        #  ROUNDING DIFFERENCE  –  post to 754 account if diff exists         #
        #  diff > 0 means our math was less than gross  → debit  754          #
        #  diff < 0 means our math was more than gross  → credit 754          #
        # ------------------------------------------------------------------ #
        # if gratuity_amount:
        #     diff_entry = {
        #         "account"                  : "715 - End of Service Indemnities - NRC" if self.get("company") == "NORTHCORP LLC" else "715 - End of Service Indemnities - NRI",
        #         "debit_in_account_currency": flt(gratuity_amount, precision),
        #         "exchange_rate"            : flt(exchange_rate),
        #         "cost_center"              : self.cost_center,
        #     }
        #     accounts.append(self.update_accounting_dimensions(diff_entry, accounting_dimensions))            
        if flt(rounding_diff, precision) != 0:
            rounding_account = frappe.db.get_value("Company",self.get("company"),"write_off_account") or ""

            if not rounding_account:
                frappe.throw(
                    _(
                        "Rounding difference account (account number 754) not found "
                        "for company {0}. Please ensure the account exists."
                    ).format(frappe.bold(self.company))
                )

            exchange_rate, diff_amt = self.get_amount_and_exchange_rate_for_journal_entry(
                rounding_account,
                abs(rounding_diff),
                company_currency,
                currencies,
            )

            # diff > 0: earnings > payable credit needed → debit 754 to absorb excess
            # diff < 0: earnings < payable credit needed → credit 754 to cover shortfall
            if rounding_diff > 0:
                diff_entry = {
                    "account"                  : rounding_account,
                    "debit_in_account_currency": flt(diff_amt, precision),
                    "exchange_rate"            : flt(exchange_rate),
                    "cost_center"              : self.cost_center,
                    "reference_type"           : "Payroll Entry",
                    "reference_name"           : self.name,
                }
            else:
                diff_entry = {
                    "account"                   : rounding_account,
                    "credit_in_account_currency": flt(diff_amt, precision),
                    "exchange_rate"             : flt(exchange_rate),
                    "cost_center"               : self.cost_center,
                    "reference_type"            : "Payroll Entry",
                    "reference_name"            : self.name,
                }

            accounts.append(self.update_accounting_dimensions(diff_entry, accounting_dimensions))

        journal_entry = self.make_journal_entry(
            accounts                         = accounts,
            currencies                       = currencies,
            payroll_payable_account          = payroll_payable_account,
            voucher_type                     = "Journal Entry",
            user_remark                      = _(
                "Accrual Journal Entry for salaries from {0} to {1}"
            ).format(self.start_date, self.end_date),
            submit_journal_entry             = True,
            submitted_salary_slips           = submitted_salary_slips,
            employee_wise_accounting_enabled = False,
        )

        return journal_entry.name if journal_entry else ""


# --------------------------------------------------------------------------- #
#  EARNINGS BREAKDOWN                                                          #
# --------------------------------------------------------------------------- #
def get_earnings_breakdown(pe=None, company=None):
    if not pe or not company:
        return []

    return frappe.db.sql(
        """
        SELECT
            base.department,
            base.payroll_cost_center,
            base.project,
            COALESCE(
                (
                    SELECT sca.account
                    FROM `tabSalary Component Account` sca
                    WHERE sca.parent     = base.salary_component
                      AND sca.department = base.department
                      AND sca.company    = %s
                    ORDER BY sca.modified DESC
                    LIMIT 1
                ),
                base.default_payroll_account
            ) AS account,
            base.salary_component,
            SUM(base.amount) AS amount
        FROM (

            -- Employees WITH project allocation (excluding Advance Payment)
            SELECT
                ss.name                              AS slip_name,
                ss.department,
                dep.payroll_cost_center,
                dep.default_payroll_account,
                al.project,
                sd.salary_component,
                SUM(sd.amount * al.percentage / 100) AS amount
            FROM
                `tabSalary Slip` ss
            INNER JOIN
                `tabProject Allocation` al
                    ON  al.parent = ss.name
            INNER JOIN
                `tabSalary Detail` sd
                    ON  sd.parent          = ss.name
                    AND sd.parentfield     = 'earnings'
                    AND sd.salary_component not in ('Advance Payment','Gratuity')
            LEFT JOIN
                `tabDepartment` dep
                    ON  dep.name = ss.department
            WHERE
                ss.payroll_entry = %s
                AND ss.docstatus  = 1
                AND sd.amount     > 0
                AND (
                    sd.do_not_include_in_total = 0
                    OR (sd.do_not_include_in_total = 1 AND sd.do_not_include_in_accounts = 0)
                )
            GROUP BY
                ss.name,
                al.project,
                sd.salary_component

            UNION ALL

            -- Employees WITHOUT project allocation (excluding Advance Payment)
            SELECT
                ss.name                 AS slip_name,
                ss.department,
                dep.payroll_cost_center,
                dep.default_payroll_account,
                NULL                    AS project,
                sd.salary_component,
                SUM(sd.amount)          AS amount
            FROM
                `tabSalary Slip` ss
            INNER JOIN
                `tabSalary Detail` sd
                    ON  sd.parent          = ss.name
                    AND sd.parentfield     = 'earnings'
                    AND sd.salary_component not in ('Advance Payment','Gratuity')
            LEFT JOIN
                `tabDepartment` dep
                    ON  dep.name = ss.department
            WHERE
                ss.payroll_entry = %s
                AND ss.docstatus  = 1
                AND sd.amount     > 0
                AND (
                    sd.do_not_include_in_total = 0
                    OR (sd.do_not_include_in_total = 1 AND sd.do_not_include_in_accounts = 0)
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM `tabProject Allocation` al
                    WHERE al.parent = ss.name
                )
            GROUP BY
                ss.name,
                sd.salary_component

        ) AS base
        GROUP BY
            base.department,
            base.project,
            base.salary_component
        """,
        (company, pe, pe),
        as_dict=True,
    )


# --------------------------------------------------------------------------- #
#  DEDUCTIONS BREAKDOWN                                                        #
# --------------------------------------------------------------------------- #
def get_deductions_breakdown(pe=None, company=None):
    if not pe or not company:
        return []

    return frappe.db.sql(
        """
        SELECT
            ss.employee,
            ss.department,
            dep.payroll_cost_center,
            COALESCE(
                (
                    SELECT sca.account
                    FROM `tabSalary Component Account` sca
                    WHERE sca.parent     = sd.salary_component
                      AND sca.department = ss.department
                      AND sca.company    = ss.company
                    LIMIT 1
                ),
                dep.default_payroll_account
            ) AS account,
            sd.salary_component,
            SUM(sd.amount) AS amount
        FROM
            `tabSalary Slip` ss
        INNER JOIN
            `tabSalary Detail` sd
                ON  sd.parent = ss.name
                AND (
                    sd.parentfield = 'deductions'
                    OR (sd.parentfield = 'earnings' AND sd.salary_component in ('Advance Payment','Gratuity'))
                )
        LEFT JOIN
            `tabDepartment` dep
                ON  dep.name = ss.department
        WHERE
            ss.payroll_entry = %s
            AND ss.docstatus  = 1
            AND sd.amount     > 0
            AND (
                sd.do_not_include_in_total = 0
                OR (sd.do_not_include_in_total = 1 AND sd.do_not_include_in_accounts = 0)
            )
        GROUP BY
            ss.employee,
            ss.department,
            sd.salary_component
        """,
        (pe),
        as_dict=True,
    )
