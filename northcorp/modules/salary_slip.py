# Copyright (c) 2021, The Nexperts Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import getdate, formatdate

def override_methods():
    from erpnext.payroll.doctype.salary_slip.salary_slip import SalarySlip
    SalarySlip.get_data_for_eval = get_data_for_eval

def before_validate(self, method):
    override_methods()

def before_save(self, method):
    override_methods()
    calculate_project_wise_allocation(self)

def before_submit(self, method):
    override_methods()

def get_data_for_eval(self):
    '''Returns data for evaluating formula'''
    # customization add cache for performance improvement
    #key = "temp_{0}".format(self.employee)
    #val = frappe.cache().get_value(key)
    #if val: return val

    data = frappe._dict()
    employee = frappe.get_doc("Employee", self.employee).as_dict()

    start_date = getdate(self.start_date)
    date_to_validate = (
        employee.date_of_joining
        if employee.date_of_joining > start_date
        else start_date
    )

    salary_structure_assignment = frappe.get_value(
        "Salary Structure Assignment",
        {
            "employee": self.employee,
            "salary_structure": self.salary_structure,
            "from_date": ("<=", date_to_validate),
            "docstatus": 1,
        },
        "*",
        order_by="from_date desc",
        as_dict=True,
    )

    if not salary_structure_assignment:
        frappe.throw(
            _("Please assign a Salary Structure for Employee {0} "
            "applicable from or before {1} first").format(
                frappe.bold(self.employee_name),
                frappe.bold(formatdate(date_to_validate)),
            )
        )

    data.update(salary_structure_assignment)
    data.update(employee)
    data.update(self.as_dict())
    self.hourly_rate = salary_structure_assignment.get("hourly_rate")

    calculate_overtime(self)

    # set values for components
    salary_components = frappe.get_all("Salary Component", fields=["salary_component_abbr"])
    for sc in salary_components:
        data.setdefault(sc.salary_component_abbr, 0)

    for key in ('earnings', 'deductions'):
        for d in self.get(key):
            data[d.abbr] = d.amount

    # customization add data in cache for performance imporvement
    #frappe.cache().set_value(key, data, expires_in_sec=100)
    return data

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
                AND att.working_hours > 1
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
                temp_list.append({
                    "project": row.get("project"),
                    "project_name": frappe.db.get_value("Project",row.get("project"),"project_name"),
                    "total_hours": row.get("working_hours"),
                    "percentage": round((row.get("working_hours")/total_hours)*100,2)
                })
            self.set("project_wise_allocation",temp_list)