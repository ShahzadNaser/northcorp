# Copyright (c) 2021, The Nexperts Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import getdate, formatdate, flt, date_diff, cint, escape_html
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip

try:
    # hrms >= 16.5x moved this from a SalarySlip method to a module-level util
    from hrms.payroll.utils import get_component_abbr_map
except ImportError:
    get_component_abbr_map = None


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

        # same record set_salary_structure_assignment() already fetched (it throws if none exists)
        salary_structure_assignment = self._salary_structure_assignment
        emp_salary_details = get_emp_salary_components(salary_structure_assignment.get("name"))

        # set before self.as_dict() below so formulas see this slip's values on the first pass
        self.hourly_rate = salary_structure_assignment.get("hourly_rate")
        if is_overtime_enabled(self.employee):
            calculate_overtime(self)
        else:
            self.overtimehours = 0

        data.update(self._salary_structure_assignment)
        data.update(self.as_dict())
        data.update(employee)

        data.update(self.get_component_abbr_zero_map())

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

    def get_component_abbr_zero_map(self):
        """{salary_component_abbr: 0} for every component, across hrms versions."""
        if get_component_abbr_map:
            return get_component_abbr_map()
        return super().get_component_abbr_map()

    def _set_evaluated_components(self):
        """hrms >= 16.5x takes each row's default_amount from the Salary Structure Assignment's
        period-independent evaluation, which never sees the per-employee components, overtime
        or gratuity set up in get_data_for_eval(). Paid amounts are prorated from default_amount,
        so flag every row for re-evaluation: add_structure_component() then computes
        default_amount against this slip's default_data, as hrms < 16.5x did."""
        super()._set_evaluated_components()

        for rows in self._evaluated_components.values():
            for row in rows:
                row.condition_met = False

    def email_salary_slip(self):
        """Based on hrms' email_salary_slip, with these differences:
        - the recipient comes from get_salary_slip_recipient()
        - the PDF is always encrypted with get_salary_slip_password(), whatever Payroll Settings
          says, and is not sent at all if there is no password
        - the email explains how to open the PDF
        Compare with the hrms method when upgrading hrms, as changes there won't apply here."""
        receiver = get_salary_slip_recipient(self.employee)
        if not receiver:
            frappe.msgprint(_("{0}: Employee email not found, hence email not sent").format(self.employee_name))
            return

        password = get_salary_slip_password(self.employee)
        if not password:
            frappe.msgprint(_("{0}: Date of Birth not found, hence email not sent").format(self.employee_name))
            return

        payroll_settings = frappe.get_single("Payroll Settings")

        subject = f"Salary Slip - from {self.start_date} to {self.end_date}"
        message = get_salary_slip_greeting(self)
        if payroll_settings.email_template:
            email_template = frappe.get_doc("Email Template", payroll_settings.email_template)
            context = self.as_dict()
            subject = frappe.render_template(email_template.subject, context)
            message = frappe.render_template(email_template.response, context)
        message += get_salary_slip_password_instructions()

        posting_date = getdate(self.posting_date)
        email_args = {
            "sender": payroll_settings.sender_email,
            "recipients": [receiver],
            "message": message,
            "subject": subject,
            "attachments": [
                frappe.attach_print(self.doctype, self.name, file_name=self.name, password=password)
            ],
            "reference_doctype": self.doctype,
            "reference_name": self.name,
            "send_after": posting_date if posting_date > getdate() else None,
        }
        if not frappe.flags.in_test:
            frappe.enqueue(method=frappe.sendmail, queue="short", timeout=300, is_async=True, **email_args)
        else:
            frappe.sendmail(**email_args)


def get_salary_slip_password(employee):
    """The employee's date of birth as DDMMYYYY, e.g. 5 March 1990 is 05031990."""
    date_of_birth = frappe.db.get_value("Employee", employee, "date_of_birth")
    return getdate(date_of_birth).strftime("%d%m%Y") if date_of_birth else None


def get_salary_slip_greeting(slip):
    return "<p>{0}</p><p>{1}</p>".format(
        _("Dear {0},").format(escape_html(slip.employee_name)),
        _("Your salary slip for {0} to {1} is attached.").format(
            formatdate(slip.start_date), formatdate(slip.end_date)
        ),
    )


def get_salary_slip_password_instructions():
    """Describes the password format only, so the email itself never contains the password."""
    return "<p><b>{0}</b></p><ol><li>{1}</li><li>{2}</li><li>{3}</li></ol><p>{4}</p><p>{5}</p>".format(
        _("How to open your salary slip"),
        _("Open the attached PDF file."),
        _("When asked for a password, enter your date of birth as DDMMYYYY, using numbers only."),
        _("For example, if you were born on 5 March 1990, enter 05031990."),
        _("Please keep this document private."),
        _("If you cannot open the file, please contact HR. This is an automated email, so please do not reply."),
    )


def get_salary_slip_recipient(employee):
    """Salary slips go to the employee's Personal Email, falling back to Preferred Email.

    Preferred Email stays the work address: leave, stock entry and asset movement
    notifications all send to it."""
    emails = frappe.db.get_value("Employee", employee, ["personal_email", "prefered_email"], as_dict=True)
    if not emails:
        return None
    return emails.get("personal_email") or emails.get("prefered_email")


def is_overtime_enabled(employee):
    """Overtime is paid only to employees with Enable Overtime checked on their profile."""
    return bool(frappe.get_cached_value("Employee", employee, "enable_overtime"))


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