# Copyright (c) 2021, The Nexperts Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import flt

def before_save(doc, method):
    if doc.base:
        emp_working_hours = frappe.db.get_value("Employee",doc.employee,'working_hours') or 8
        emp_working_days = frappe.db.get_value("Department",doc.department,'working_days') or 30
        total_salary = flt(doc.base)
        for row in doc.employee_salary_components:
            if row.hourly:
                total_salary += flt(row.amount)
        doc.hourly_rate = round(total_salary/(emp_working_days*emp_working_hours), 2)
