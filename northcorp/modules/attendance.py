# Copyright (c) 2022, Shahzad Naser and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt
from hrms.utils.holiday_list import get_holiday_list_for_employee

def before_submit(doc, method):
    calculate_overtime(doc)


def get_attendance_holiday_list(doc):
    """Holiday list in effect on the attendance date (hrms assigns them by date)."""
    holiday_list = get_holiday_list_for_employee(
        doc.employee, raise_exception=False, as_on=doc.attendance_date
    )
    if not holiday_list:
        # legacy fields from before Holiday List Assignment
        holiday_list = frappe.db.get_value("Employee", doc.employee, "holiday_list") or frappe.get_cached_value(
            "Company", doc.company, "default_holiday_list"
        )
    return holiday_list

def calculate_overtime(doc):
    """Customization calculate overtime according to requirements"""
    emp_working_hours = frappe.db.get_value("Employee",doc.employee,'working_hours') or 8
    temp_working_hours = 0
    for row in doc.project_wise_attendance:
        temp_working_hours += row.working_hours

    doc.working_hours = flt(temp_working_hours)
    att_date = frappe.utils.getdate(doc.attendance_date)
    att_day = att_date.strftime('%A')

    holiday_list = get_attendance_holiday_list(doc)
    if holiday_list and frappe.db.exists(
        "Holiday", {"parent": holiday_list, "parenttype": "Holiday List", "holiday_date": att_date}
    ):
        att_day = 'Sunday'

    
    if doc.working_hours:
        if att_day == 'Saturday':
            emp_working_hours = emp_working_hours - 2
            if doc.working_hours >= emp_working_hours:
                doc.overtime_hours =(doc.working_hours - emp_working_hours)
            else:
                doc.short_hours = emp_working_hours - doc.working_hours
        elif att_day == 'Sunday':
            doc.overtime_hours = doc.working_hours * 1.5
        else:
            if doc.working_hours >= emp_working_hours:
                doc.overtime_hours = doc.working_hours - emp_working_hours
            else:
                doc.short_hours = emp_working_hours - doc.working_hours

