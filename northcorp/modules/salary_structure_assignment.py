# Copyright (c) 2021, The Nexperts Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import flt
from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
    SalaryStructureAssignment,
)


class CustomSalaryStructureAssignment(SalaryStructureAssignment):
    def _get_component_eval_context(self):
        """hrms >= 16.5x evaluates structure formulas on the assignment itself (slip defaults,
        CTC / gross). Expose this employee's own component amounts there, the same way
        CustomSalarySlip.get_data_for_eval() does for the slip."""
        data = super()._get_component_eval_context()
        for row in self.get("employee_salary_components"):
            if row.abbr and flt(row.amount):
                data[row.abbr] = flt(row.amount)
        return data


def before_save(doc, method):
    if doc.base:
        emp_working_hours = frappe.db.get_value("Employee",doc.employee,'working_hours') or 8
        emp_working_days = frappe.db.get_value("Department",doc.department,'working_days') or 30
        total_salary = flt(doc.base)
        for row in doc.employee_salary_components:
            if row.hourly:
                total_salary += flt(row.amount)
        doc.hourly_rate = round(total_salary/(emp_working_days*emp_working_hours), 2)
