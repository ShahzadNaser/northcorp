# Copyright (c) 2021, The Nexperts Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import getdate, formatdate, flt, date_diff, cint
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

def before_save(self, method):
    # override_methods()
    calculate_project_wise_allocation(self)


class CustomSalarySlip(SalarySlip):
    def get_data_for_eval(self):
        """Returns data for evaluating formula"""
        data = frappe._dict()
        employee = frappe.get_cached_doc("Employee", self.employee).as_dict()

        if not hasattr(self, "_salary_structure_assignment"):
            self.set_salary_structure_assignment()

        data.update(self._salary_structure_assignment)
        data.update(self.as_dict())
        data.update(employee)

        data.update(self.get_component_abbr_map())

        salary_structure_assignment = frappe.get_value(
            "Salary Structure Assignment",
            {
                "employee": self.employee,
                "salary_structure": self.salary_structure,
                "from_date": ("<=", self.actual_start_date),
                "docstatus": 1,
            },
            "*",
            order_by="from_date desc",
            as_dict=True,
        )
        emp_salary_details = get_emp_salary_components(salary_structure_assignment.get("name"))

        self.hourly_rate = salary_structure_assignment.get("hourly_rate")

        if data.get("enable_overtime"):
            calculate_overtime(self)

        if not data.get("disable_gratuity") and not self.get("gratuity_amount"):
            self.gratuity_amount = calculate_total_gratuity(self.get("employee"), data.get("gratuity_account"), data.get("base"), data.get("date_of_joining"), self.get("end_date"))

        # shallow copy of data to store default amounts (without payment days) for tax calculation
        default_data = data.copy()

        for key in ("earnings", "deductions"):
            for d in self.get(key):
                data[d.abbr] = d.amount or 0

        # set values for components
        salary_components = frappe.get_all("Salary Component", fields=["salary_component_abbr"])
        for sc in salary_components:
            data.setdefault(sc.salary_component_abbr, emp_salary_details.get(sc.salary_component_abbr) or 0)
            default_data[sc.salary_component_abbr] = emp_salary_details.get(sc.salary_component_abbr) or 0

        return data, default_data


    def make_loan_repayment_entry(self):
        from erpnext.loan_management.doctype.loan_repayment.loan_repayment import create_repayment_entry
        for loan in self.loans:
            repayment_entry = create_repayment_entry(loan.loan, self.employee,
                self.company, self.posting_date, loan.loan_type, "Regular Payment", loan.interest_amount,
                loan.principal_amount, loan.total_payment)

            repayment_entry.payroll_entry = self.get("payroll_entry")
            repayment_entry.save()
            repayment_entry.submit()

            frappe.db.set_value("Salary Slip Loan", loan.name, "loan_repayment_entry", repayment_entry.name)


def calculate_overtime(self):
    overtime = frappe.db.sql('''
        SELECT 
            SUM(overtime_hours) as overtimehours
        FROM
            tabAttendance
        WHERE
            status = 'Present' AND docstatus = 1
                AND working_hours > 1
                AND attendance_date BETWEEN %s AND %s
                AND employee = %s    
    ''', (self.start_date, self.end_date, self.employee), as_dict=True)
    self.overtimehours = overtime[0].get("overtimehours") or 0

def calculate_project_wise_allocation(self):
    project_wise_time = frappe.db.sql('''
        SELECT 
            att_time.project as project,
            SUM(att_time.working_hours) as working_hours
        FROM
            `tabAttendance` att
        LEFT JOIN 
            `tabAttendance Time` att_time
            ON
                att_time.parent = att.name
        WHERE
            att.status = 'Present' AND att.docstatus = 1
                AND att.working_hours > 0
                AND att.attendance_date BETWEEN %s AND %s
                AND att.employee = %s    
        GROUP BY
            att_time.project
    ''', (self.start_date, self.end_date, self.employee), as_dict=True)
    if(project_wise_time):
        total_hours = sum(d.get('working_hours', 0) for d in project_wise_time)
        if(total_hours):
            temp_list = []
            for row in project_wise_time:
                per = round((flt(row.get("working_hours"))/flt(total_hours))*100,2)
                temp_list.append({
                    "project": row.get("project"),
                    "project_name": frappe.db.get_value("Project",row.get("project"),"project_name"),
                    "total_hours": row.get("working_hours"),
                    "percentage": per,
                    "amount": flt((per * (flt(self.rounded_total) + flt(self.get("total_loan_repayment"))))/100)            
                })
            self.set("project_wise_allocation",temp_list)
    else:
        default_project = frappe.db.get_value("Company",self.company,"default_project")
        if default_project:
            self.set("project_wise_allocation",[{
                    "project": default_project,
                    "project_name": frappe.db.get_value("Project",default_project,"project_name"),
                    "total_hours": 0,
                    "percentage": 100,
                    "amount": flt(flt(self.rounded_total) + flt(self.get("total_loan_repayment")))               
                }])
        

def get_emp_salary_components(salary_structure_assignment):
    if not salary_structure_assignment:
        return {}

    esc =  frappe.get_all("Employee Salary Components", filters={"parent": salary_structure_assignment}, fields=["salary_component","abbr","amount"])
    emp_salary_details = {}
    for row in esc:
        if row.get("amount"):
            emp_salary_details[row.get("abbr")] = row.get("amount")

    return emp_salary_details

def get_gratuity_sanctioned_amount(employee, gratuity_account):
    """
    Returns SUM(credit - debit) from GL Entry
    for given employee and gratuity account.
    Only considers non-cancelled entries.
    """
    result = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(credit) - SUM(debit), 0) AS sanctioned_amount
        FROM
            `tabGL Entry`
        WHERE
            party_type   = 'Employee'
            AND party    = %s
            AND account  = %s
            AND is_cancelled = 0
        """,
        (employee, gratuity_account),
        as_dict=True
    )
    return flt(result[0].sanctioned_amount) if result else 0.0

def calculate_total_gratuity(employee, gratuity_account, basic_salary, date_of_joining, as_of_date):
    """
    Calculates total accrued UAE gratuity as of a given date.

    Rules (Article 51, Federal Decree Law No. 33 of 2021):
        < 1 year   : 0
        1–5 years  : (basic/30) * 21 * days / 365
        > 5 years  : (basic/30) * (21*5 + 30*(days-1825)/365)
        cap        : basic * 24  (2 years salary maximum)

    Args:
        basic_salary   : float  — current basic salary
        date_of_joining: str    — employee joining date
        as_of_date     : str    — calculate as of this date (usually payroll end date)

    Returns:
        float — total accrued gratuity rounded to 2 decimal places
    """
    doj           = getdate(date_of_joining)
    as_of         = getdate(as_of_date)
    lwp = cint(abs(get_unpaid_leave_days(employee, date_of_joining, as_of_date)))
    eligible_days = (date_diff(as_of, doj)+1) - lwp
    daily_rate    = flt(basic_salary) / 30

    ONE_YEAR   = 365
    FIVE_YEARS = 1825

    if eligible_days < ONE_YEAR:
        total = 0.0

    elif eligible_days <= FIVE_YEARS:
        # 21 days per year for first 5 years
        total = daily_rate * 21 * eligible_days / 365

    else:
        # 21 days/year for first 5 years + 30 days/year beyond 5 years
        total = daily_rate * (21 * 5 + 30 * (eligible_days - FIVE_YEARS) / 365)

    # Cap at 24 months basic salary
    cap   = flt(basic_salary) * 24
    total = min(total, cap)
    sanctioned_amount = get_gratuity_sanctioned_amount(employee, gratuity_account)
    total  = flt(total) - flt(sanctioned_amount)
    return round(max(total,0), 2)

def get_unpaid_leave_days(employee, date_of_joining, as_of_date):
    """
    Returns total cumulative Leave Without Pay (LWP) days
    for an employee from date of joining up to as_of_date.
    Source: Leave Ledger Entry for leave types marked as is_lwp = 1.
    """
    result = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(lle.leaves), 0) AS lwp_days
        FROM
            `tabLeave Ledger Entry` lle
       
        WHERE
            lle.employee     = %s
            AND lle.from_date >= %s
            AND lle.to_date   <= %s
            AND lle.docstatus  = 1
            AND lle.is_expired = 0
            AND lle.is_lwp = 1
            AND lle.is_lwp = 1
            AND lle.transaction_type = 'Leave Application'
        """,
        (employee, date_of_joining, as_of_date),
        as_dict=True,debug=True
    )
    return flt(result[0].lwp_days) if result else 0.