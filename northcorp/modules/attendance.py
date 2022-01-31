# Copyright (c) 2022, Shahzad Naser and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt

def before_submit(doc, method):
    calculate_overtime(doc)

def calculate_overtime(doc):
    """Customization calculate overtime according to requirements"""
    emp_working_hours = frappe.db.get_value("Employee",doc.employee,'working_hours') or 8
    temp_working_hours = 0
    for row in doc.project_wise_attendance:
        temp_working_hours += row.working_hours

    doc.working_hours = flt(temp_working_hours)

    if doc.working_hours:
        if doc.working_hours >= emp_working_hours:
            doc.overtime_hours = doc.working_hours - emp_working_hours
        else:
            doc.short_hours = emp_working_hours - doc.working_hours

