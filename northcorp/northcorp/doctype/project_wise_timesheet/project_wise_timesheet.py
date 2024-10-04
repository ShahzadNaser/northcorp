# Copyright (c) 2022, Shahzad Naser and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document
from datetime import timedelta, date
from frappe.utils import flt

class ProjectWiseTimesheet(Document):
    def validate(self):
        if frappe.utils.getdate(self.start_date) > frappe.utils.getdate(self.end_date):
            frappe.throw("From Date cannot be greater than End Date.")

        if frappe.utils.getdate(self.end_date) > frappe.utils.getdate(frappe.utils.nowdate()):
            frappe.throw("End Date cannot be greater than {}".format(
                frappe.utils.nowdate()))

        # self.validate_duplicate_date_rows()
    def on_trash():
        pass

    def validate_duplicate_date_rows(self):
        temp_dict = {}
        for row in self.employees:
            if row.employee not in temp_dict:
                temp_dict[row.employee] = [row.attendance_date]
            else:
                if row.attendance_date in temp_dict[row.employee]:
                    frappe.throw("There are duplicate Attendance of Employee {0} on Date {1}".format(
                        row.employee, row.attendance_date))
                else:
                    temp_dict[row.employee].append(row.attendance_date)

    @frappe.whitelist()
    def fill_employees(self):
        self.set('employees', [])
        employees = self.get_emp_list()
        if not employees:
            error_msg = _("No employees found for the mentioned criteria.")
            frappe.throw(error_msg, title=_("No employees found"))

        for d in employees:
            for single_date in daterange(frappe.utils.getdate(self.start_date), frappe.utils.getdate(self.end_date)):
                self.append('employees', {"employee": d.employee, "attendance_date": frappe.utils.getdate(single_date), "day": frappe.utils.get_weekday(
                    frappe.utils.get_datetime(single_date)), "project": self.default_project or '', "start_time": '', "end_time": ''})

        self.number_of_employees = len(self.employees)

    def before_submit(self):
        if self.employees:
            for emp in self.employees:
                if not emp.working_hours and (not emp.start_time or not emp.end_time):
                    frappe.throw(
                        _("Working Hours or Start Time and End Time required in Employee Timesheet for Employee {}".format(emp.employee)))
                if emp.start_time and emp.end_time:
                    emp.working_hours = frappe.utils.time_diff_in_hours(
                        emp.end_time, emp.start_time)

                if emp.working_hours <= 0:
                    frappe.throw(
                        _("Working Hours cannot be Zero in Employee Timesheet for Employee {}".format(emp.employee)))

                if not emp.project:
                    frappe.throw(
                        _("There is not Project selected in Employee Timesheet for Employee {}".format(emp.employee)))

        else:
            frappe.throw(
                "There must be atlease one entry in Employee Timesheet")

    def on_submit(self):
        #frappe.enqueue(mark_attendance, timeout=6000,
        #               is_async=True, now=True, self=self)
        mark_attendance(self=self)

    def on_cancel(self):
        frappe.enqueue(cancel_attendance, timeout=6000,is_async=True, now=True, self=self)

    def get_emp_list(self):
        cond = self.get_filter_condition()
        return frappe.db.sql("""
			select
				name as employee
			from
				`tabEmployee` emp
			where
				%s
			order by emp.name asc
		""" % cond, as_dict=True, debug=True)

    def get_filter_condition(self):
        conditions = "emp.status != 'Inactive' "

        if self.get("department"):
            conditions += " and emp.department = '{0}' ".format(
                self.get("department"))
        if self.get("branch"):
            conditions += " and emp.branch = '{0}' ".format(self.get("branch"))
        if self.get("designation"):
            conditions += " and emp.designation = '{0}' ".format(
                self.get("designation"))
        if self.get("employee_grade"):
            conditions += " and emp.name = '{0}' ".format(
                self.get("employee_grade"))

        if self.get("employee_inclusion"):
            employee_inclusion = get_employee_ids(
                frappe.parse_json(self.get('employee_inclusion')))
            conditions += " and emp.name in ({0}) ".format(
                ','.join("'{0}'".format(x.employee) for x in employee_inclusion))

        if self.get("employee_exclusion"):
            employee_exclusion = get_employee_ids(
                frappe.parse_json(self.get('employee_exclusion')))
            conditions += " and emp.name not in ({0}) ".format(
                ','.join("'{0}'".format(x.employee) for x in employee_exclusion))

        return conditions


def get_employee_ids(employees):
    if not isinstance(employees, list):
        employees = [d.strip() for d in employees.strip().split(',') if d]

    return employees


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days)+1):
        yield start_date + timedelta(n)

@frappe.whitelist()
def cancel_attendance(self, publish_progress=True):
    temp_dict = {}
    for row in self.employees:
        if row.employee not in temp_dict:
            temp_dict[row.employee] = {row.attendance_date: [{"project": row.project, "working_hours": row.working_hours}]}
        else:
            if row.attendance_date not in temp_dict[row.employee]:
                temp_dict[row.employee][row.attendance_date] = [{"project": row.project, "working_hours": row.working_hours}]
            else:
                temp_dict[row.employee][row.attendance_date].append({"project": row.project, "working_hours": row.working_hours})
    
    for employee, employee_dict in temp_dict.items():
        for attendance_date, time_list in employee_dict.items():

            existing_attnd = frappe.db.get_value("Attendance", {'employee': employee, 'attendance_date': attendance_date,'docstatus':1}, 'name')
            if existing_attnd:
                attendance_doc = frappe.get_doc("Attendance", existing_attnd)
                lst_time_doc = []
                for times in attendance_doc.project_wise_attendance:
                    lst_time_doc.append(times.project_wise_timesheet)
                time_doc = set(lst_time_doc)
                remove = []
                if len(time_doc) > 1:
                    for times in attendance_doc.project_wise_attendance:
                        if self.name == times.project_wise_timesheet:
                            remove.append(times)
                    [attendance_doc.remove(d) for d in remove]
                    attendance_doc.save()
                    frappe.db.commit()
                    emp_working_hours = frappe.db.get_value("Employee",employee,'working_hours') or 8
                    temp_working_hours = 0
                    for row in attendance_doc.project_wise_attendance:
                        temp_working_hours += row.working_hours

                    frappe.db.set_value("Attendance",existing_attnd,'working_hours',flt(temp_working_hours))
                    if attendance_doc.working_hours:
                        att_date = frappe.utils.getdate(attendance_doc.attendance_date)
                        att_day = att_date.strftime('%A')
                        if att_day == 'Saturday':
                            frappe.errprint(att_day)
                            emp_working_hours = emp_working_hours - 2
                            frappe.errprint(emp_working_hours)
                            frappe.errprint(flt(temp_working_hours))
                            if flt(temp_working_hours) >= emp_working_hours:
                                frappe.db.set_value("Attendance",existing_attnd,'overtime_hours',flt(temp_working_hours) - emp_working_hours)
                            else:
                                frappe.errprint('hrllokoo')
                                frappe.errprint(existing_attnd)
                                frappe.db.set_value("Attendance",existing_attnd,'overtime_hours',0)
                                frappe.errprint(emp_working_hours - flt(temp_working_hours))
                                frappe.db.set_value("Attendance",existing_attnd,'short_hours',emp_working_hours - flt(temp_working_hours))
                        elif att_day == 'Sunday':
                            frappe.db.set_value("Attendance",existing_attnd,'overtime_hours',flt(temp_working_hours)*1.5)
                        else:
                            if flt(temp_working_hours) >= emp_working_hours:
                                frappe.db.set_value("Attendance",existing_attnd,'overtime_hours',flt(temp_working_hours) - emp_working_hours)
                            else:
                                frappe.db.set_value("Attendance",existing_attnd,'short_hours',emp_working_hours - flt(temp_working_hours))

                else:
                    attendance_doc.cancel()
                frappe.db.commit()

@frappe.whitelist()
def mark_attendance(self, publish_progress=True):
    temp_dict = {}
    for row in self.employees:
        if row.employee not in temp_dict:
            temp_dict[row.employee] = {row.attendance_date: [
                {"project": row.project, "working_hours": row.working_hours}]}
        else:
            if row.attendance_date not in temp_dict[row.employee]:
                temp_dict[row.employee][row.attendance_date] = [
                    {"project": row.project, "working_hours": row.working_hours}]
            else:
                temp_dict[row.employee][row.attendance_date].append(
                    {"project": row.project, "working_hours": row.working_hours})

    for employee, employee_dict in temp_dict.items():
        for attendance_date, time_list in employee_dict.items():
            try:
                existing_attnd = frappe.db.get_value(
                        "Attendance", {'employee': employee, 'attendance_date': attendance_date,'docstatus':1}, 'name')
                if existing_attnd:
                    time_seq = frappe.db.sql("""select parent,attendance_date,start_time,end_time,employee from `tabEmployee Timesheet` where employee='%s' and attendance_date='%s' and docstatus = 1 and parent != '%s'"""%(employee,attendance_date,self.name),as_dict=1)
                    frappe.errprint(time_list)
                    for time in self.employees:
                        for old_time in time_seq:
                            oldtimehour = old_time.start_time.split(':')[0]
                            newtimehour = time.start_time.split(":")[0]
                            oldtimehourend = old_time.end_time.split(':')[0]
                            newtimehourend = time.end_time.split(":")[0]
                            try:
                                oldtimehour = int(oldtimehour)
                            except:
                                oldtimehour = int(oldtimehour[1])

                            try:
                                newtimehour = int(newtimehour)
                            except:
                                newtimehour = int(newtimehour[1])

                            try:
                                oldtimehourend = int(oldtimehourend)
                            except:
                                oldtimehourend = int(oldtimehourend[1])

                            try:
                                newtimehourend = int(newtimehourend)
                            except:
                                newtimehourend = int(newtimehourend[1])

                            new_time_list = []
                            for newtime in range(newtimehour,newtimehourend):
                                new_time_list.append(newtime)

                            old_time_list = []
                            for oldtime in range(oldtimehour,oldtimehourend):
                                old_time_list.append(oldtime)
                            
                            for newtimedata in new_time_list:
                                if newtimedata in old_time_list:
                                    frappe.throw("Time sheet already exist for hours {}".format(newtimedata))
                                     
                        
                    attendance_doc = frappe.get_doc(
                        "Attendance", existing_attnd)
                    
                    for time in time_list:
                        time['project_wise_timesheet'] = self.name
                        attendance_doc.append("project_wise_attendance", time)
                    attendance_doc.flags.ignore_permissions = True
                    attendance_doc.flags.ignore_mandatory = True
                    attendance_doc.save()
                    frappe.db.commit()
                    emp_working_hours = frappe.db.get_value("Employee",employee,'working_hours') or 8
                    temp_working_hours = 0
                    
                    for row in attendance_doc.project_wise_attendance:
                        frappe.errprint(row.__dict__)
                        temp_working_hours += row.working_hours

                    frappe.errprint(temp_working_hours)
                    frappe.db.set_value("Attendance",existing_attnd,'working_hours',flt(temp_working_hours))
                    if attendance_doc.working_hours:
                        att_date = frappe.utils.getdate(attendance_doc.attendance_date)
                        att_day = att_date.strftime('%A')   
                        if att_day == 'Saturday':
                            frappe.errprint(att_day)
                            emp_working_hours = emp_working_hours - 2
                            frappe.errprint(emp_working_hours)
                            frappe.errprint(attendance_doc.working_hours)
                            
                            if flt(temp_working_hours) >= emp_working_hours:
                                frappe.db.set_value("Attendance",existing_attnd,'overtime_hours',flt(temp_working_hours) - emp_working_hours)
                            else:
                                frappe.db.set_value("Attendance",existing_attnd,'short_hours',emp_working_hours - flt(temp_working_hours))
                        elif att_day == 'Sunday':
                            frappe.db.set_value("Attendance",existing_attnd,'overtime_hours',flt(temp_working_hours)*1.5)
                        else:
                            if flt(temp_working_hours) >= emp_working_hours:
                                frappe.db.set_value("Attendance",existing_attnd,'overtime_hours',flt(temp_working_hours) - emp_working_hours)
                            else:
                                frappe.db.set_value("Attendance",existing_attnd,'short_hours',emp_working_hours - flt(temp_working_hours))
                

                else:
                    attendance_doc = frappe.new_doc("Attendance")
                    attendance_doc.employee = employee
                    attendance_doc.attendance_date = attendance_date
                    attendance_doc.reference_timesheet = self.name
                    attendance_doc.status = "Present"
                    for times in time_list:
                        times['project_wise_timesheet'] = self.name
                    attendance_doc.set("project_wise_attendance", time_list)
                    attendance_doc.flags.ignore_permissions = True
                    attendance_doc.flags.ignore_mandatory = True
                    attendance_doc.save()
                    attendance_doc.submit()
            except Exception as error:
                traceback = frappe.get_traceback()
                frappe.throw(traceback)
                continue
