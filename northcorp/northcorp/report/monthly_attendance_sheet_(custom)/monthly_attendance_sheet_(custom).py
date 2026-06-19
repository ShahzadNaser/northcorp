# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _, msgprint
from frappe.utils import cint, cstr, getdate, add_days, date_diff

status_map = {
	"Absent": "A",
	"Half Day": "HD",
	"Holiday": "<b>H</b>",
	"Weekly Off": "<b>WO</b>",
	"On Leave": "L",
	"Present": "P",
	"Work From Home": "WFH",
}

day_abbr = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def execute(filters=None):
	if not filters:
		filters = {}

	# Build the list of dates this report covers (the heart of the change).
	conditions, filters = get_conditions(filters)
	date_list = filters["date_list"]

	columns, days = get_columns(filters)
	att_map = get_attendance_list(conditions, filters)

	if not att_map:
		return columns, [], None, None

	if filters.group_by:
		emp_map, group_by_parameters = get_employee_details(filters.group_by, filters.company)
		holiday_list = []
		for parameter in group_by_parameters:
			h_list = [
				emp_map[parameter][d]["holiday_list"]
				for d in emp_map[parameter]
				if emp_map[parameter][d]["holiday_list"]
			]
			holiday_list += h_list
	else:
		emp_map = get_employee_details(filters.group_by, filters.company)
		holiday_list = [emp_map[d]["holiday_list"] for d in emp_map if emp_map[d]["holiday_list"]]

	default_holiday_list = frappe.get_cached_value(
		"Company", filters.get("company"), "default_holiday_list"
	)
	holiday_list.append(default_holiday_list)
	holiday_list = list(set(holiday_list))
	holiday_map = get_holiday(holiday_list, filters)

	data = []

	leave_list = None
	if filters.summarized_view:
		leave_types = frappe.db.sql("""select name from `tabLeave Type`""", as_list=True)
		leave_list = [d[0] + ":Float:120" for d in leave_types]
		columns.extend(leave_list)
		columns.extend(
			[_("Total Late Entries") + ":Float:120", _("Total Early Exits") + ":Float:120"]
		)

	if filters.group_by:
		emp_att_map = {}

		for parameter in group_by_parameters:
			emp_map_set = set([key for key in emp_map[parameter].keys()])
			if emp_map_set:
				# The group header row must be exactly as wide as a data row,
				# which is exactly as wide as `columns`. First cell holds the
				# group label, the rest are blank.
				parameter_row = ["<b>" + parameter + "</b>"] + ["" for _i in range(len(columns) - 1)]
				data.append(parameter_row)
				record, emp_att_data = add_data(
					emp_map[parameter],
					att_map,
					filters,
					holiday_map,
					conditions,
					default_holiday_list,
					leave_list=leave_list,
				)
				emp_att_map.update(emp_att_data)
				data += record
	else:
		record, emp_att_map = add_data(
			emp_map,
			att_map,
			filters,
			holiday_map,
			conditions,
			default_holiday_list,
			leave_list=leave_list,
		)
		data += record

	return columns, data


def get_chart_data(emp_att_map, days):
	labels = []
	datasets = [
		{"name": "Absent", "values": []},
		{"name": "Present", "values": []},
		{"name": "Leave", "values": []},
	]
	for idx, day in enumerate(days, start=0):
		labels.append(day.replace("::65", ""))
		total_absent_on_day = 0
		total_leave_on_day = 0
		total_present_on_day = 0
		for emp in emp_att_map.keys():
			if emp_att_map[emp][idx]:
				if emp_att_map[emp][idx] == "A":
					total_absent_on_day += 1
				if emp_att_map[emp][idx] in ["P", "WFH"]:
					total_present_on_day += 1
				if emp_att_map[emp][idx] == "HD":
					total_present_on_day += 0.5
					total_leave_on_day += 0.5
				if emp_att_map[emp][idx] == "L":
					total_leave_on_day += 1

		datasets[0]["values"].append(total_absent_on_day)
		datasets[1]["values"].append(total_present_on_day)
		datasets[2]["values"].append(total_leave_on_day)

	chart = {"data": {"labels": labels, "datasets": datasets}}
	chart["type"] = "line"
	return chart


def add_data(employee_map, att_map, filters, holiday_map, conditions, default_holiday_list, leave_list=None):
	record = []
	emp_att_map = {}
	date_list = filters["date_list"]

	for emp in employee_map:
		emp_det = employee_map.get(emp)

		row = []
		if filters.group_by:
			row += [" "]
		row += [emp, emp_det.employee_name]

		total_p = total_a = total_l = total_h = total_um = 0.0
		emp_status_map = []
		total_hours = 0
		total_overtime = 0
		total_shorttime = 0
		total_absent = 0
		total_leave = 0

		for date_str in date_list:
			d = getdate(date_str)
			status = None
			try:
				status_data = att_map.get(emp).get(date_str)
			except Exception:
				status_data = []

			if status_data:
				status = status_data[0]

			if status is None and holiday_map:
				emp_holiday_list = emp_det.holiday_list if emp_det.holiday_list else default_holiday_list
				if emp_holiday_list in holiday_map:
					for ele in holiday_map[emp_holiday_list]:
						# ele[0] is the holiday date (string), ele[1] is weekly_off flag
						if cstr(ele[0]) == date_str:
							if ele[1]:
								status = "Weekly Off"
							else:
								status = "Holiday"
							total_h += 1
							break

			abbr = status_map.get(status, "")

			if status_data:
				if status_data[1] == 0:
					emp_status_map.append("L")
					total_leave = total_leave + 1
				else:
					emp_status_map.append(round(status_data[1], 2))
					total_hours = total_hours + status_data[1]
					total_overtime = total_overtime + status_data[2]
					total_shorttime = total_shorttime + status_data[3]
			else:
				if abbr:
					emp_status_map.append(abbr)
				else:
					emp_status_map.append('<span style="color:red"><b>A</b></span>')
					total_absent = total_absent + 1

			if filters.summarized_view:
				if status == "Present" or status == "Work From Home":
					total_p += 1
				elif status == "Absent":
					total_a += 1
				elif status == "On Leave":
					total_l += 1
				elif status == "Half Day":
					total_p += 0.5
					total_a += 0.5
					total_l += 0.5
				elif not status:
					total_um += 1

		emp_status_map.append(emp_det.working_hours)
		emp_status_map.append(total_hours)
		emp_status_map.append(total_overtime)
		emp_status_map.append(total_shorttime)
		emp_status_map.append(total_absent)
		emp_status_map.append(total_leave)

		if not filters.summarized_view:
			row += emp_status_map

		if filters.summarized_view:
			row += [total_p, total_l, total_a, total_h, total_um]

		if not filters.get("employee"):
			filters.update({"employee": emp})
			conditions += " and employee = %(employee)s"
		elif not filters.get("employee") == emp:
			filters.update({"employee": emp})

		if filters.summarized_view:
			leave_details = frappe.db.sql(
				"""select leave_type, status, count(*) as count from `tabAttendance`
				where leave_type is not NULL %s group by leave_type, status"""
				% conditions,
				filters,
				as_dict=1,
			)

			time_default_counts = frappe.db.sql(
				"""select (select count(*) from `tabAttendance` where
				late_entry = 1 %s) as late_entry_count, (select count(*) from tabAttendance where
				early_exit = 1 %s) as early_exit_count"""
				% (conditions, conditions),
				filters,
			)

			leaves = {}
			for d in leave_details:
				if d.status == "Half Day":
					d.count = d.count * 0.5
				if d.leave_type in leaves:
					leaves[d.leave_type] += d.count
				else:
					leaves[d.leave_type] = d.count

			for d in leave_list:
				if d in leaves:
					row.append(leaves[d])
				else:
					row.append("0.0")

			row.extend([time_default_counts[0][0], time_default_counts[0][1]])

		emp_att_map[emp] = emp_status_map
		record.append(row)

	return record, emp_att_map


def get_columns(filters):
	columns = []

	if filters.group_by:
		# Map the selected group-by field to its underlying doctype so the
		# header cell renders as a proper link instead of always pointing at
		# Branch. Falls back to a plain Data column if unknown.
		group_by_doctype = {
			"Branch": "Branch",
			"Grade": "Employee Grade",
			"Department": "Department",
			"Designation": "Designation",
		}.get(filters.group_by)
		if group_by_doctype:
			columns = [_(filters.group_by) + ":Link/" + group_by_doctype + ":120"]
		else:
			columns = [_(filters.group_by) + ":Data:120"]

	columns += [_("Employee") + ":Link/Employee:120", _("Employee Name") + ":Data/:120"]

	days = []
	for date_str in filters["date_list"]:
		d = getdate(date_str)
		# Header shows day-of-month with weekday abbreviation, e.g. "1 Mon"
		label = cstr(d.day) + " " + day_abbr[d.weekday()]
		days.append(label + "::65")

	if not filters.summarized_view:
		columns += days
		columns += [
			_("WH") + "::65",
			_("TWH") + ":Currency:65",
			_("TOT") + ":Currency:65",
			_("TSH") + ":Currency:65",
			_("TA") + "::65",
			_("TL") + ":Currency:65",
		]

	if filters.summarized_view:
		columns += [
			_("Total Present") + ":Float:120",
			_("Total Leaves") + ":Float:120",
			_("Total Absent") + ":Float:120",
			_("Total Holidays") + ":Float:120",
			_("Unmarked Days") + ":Float:120",
		]

	return columns, days


def get_attendance_list(conditions, filters):
	attendance_list = frappe.db.sql(
		"""select employee, attendance_date, working_hours, overtime_hours, short_hours, status
		from tabAttendance where docstatus = 1 %s order by employee, attendance_date"""
		% conditions,
		filters,
		as_dict=1,
	)

	if not attendance_list:
		msgprint(_("No attendance record found"), alert=True, indicator="orange")

	att_map = {}
	for d in attendance_list:
		key = cstr(getdate(d.attendance_date))
		att_map.setdefault(d.employee, frappe._dict()).setdefault(key, "")
		att_map[d.employee][key] = [d.status, d.working_hours, d.overtime_hours, d.short_hours]

	return att_map


def get_conditions(filters):
	"""Date range is now the primary driver. Month/year are optional fallbacks."""
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	# Fall back to month/year if no explicit range was given.
	if not (from_date and to_date):
		if not (filters.get("month") and filters.get("year")):
			msgprint(_("Please select a date range (or month and year)"), raise_exception=1)

		from calendar import monthrange

		total_days = monthrange(cint(filters.year), cint(filters.month))[1]
		from_date = "%s-%02d-01" % (cint(filters.year), cint(filters.month))
		to_date = "%s-%02d-%02d" % (cint(filters.year), cint(filters.month), total_days)
		filters["from_date"] = from_date
		filters["to_date"] = to_date

	from_date = getdate(from_date)
	to_date = getdate(to_date)

	if from_date > to_date:
		msgprint(_("From Date cannot be after To Date"), raise_exception=1)

	# Build an explicit, ordered list of date strings for the range.
	date_list = []
	d = from_date
	while d <= to_date:
		date_list.append(cstr(d))
		d = add_days(d, 1)

	filters["date_list"] = date_list
	filters["from_date"] = cstr(from_date)
	filters["to_date"] = cstr(to_date)
	# kept for any downstream references
	filters["total_days_in_month"] = len(date_list)

	conditions = " and attendance_date between %(from_date)s and %(to_date)s"

	if filters.get("company"):
		conditions += " and company = %(company)s"
	if filters.get("employee"):
		conditions += " and employee = %(employee)s"

	return conditions, filters


def get_employee_details(group_by, company):
	emp_map = {}
	query = """select name, employee_name, designation, working_hours, department, branch, company,
		holiday_list from `tabEmployee` where company = %s and status = 'Active'""" % frappe.db.escape(company)

	if group_by:
		group_by = group_by.lower()
		query += " order by " + group_by + " ASC"

	employee_details = frappe.db.sql(query, as_dict=1)

	group_by_parameters = []
	if group_by:
		group_by_parameters = list(
			set(detail.get(group_by, "") for detail in employee_details if detail.get(group_by, ""))
		)
		for parameter in group_by_parameters:
			emp_map[parameter] = {}

	for d in employee_details:
		if group_by and len(group_by_parameters):
			if d.get(group_by, None):
				emp_map[d.get(group_by)][d.name] = d
		else:
			emp_map[d.name] = d

	if not group_by:
		return emp_map
	else:
		return emp_map, group_by_parameters


def get_holiday(holiday_list, filters):
	"""Fetch holidays across the whole date range, keyed by holiday list.
	Each entry is (holiday_date_string, weekly_off)."""
	holiday_map = frappe._dict()
	for d in holiday_list:
		if d:
			holiday_map.setdefault(
				d,
				frappe.db.sql(
					"""select holiday_date, weekly_off from `tabHoliday`
					where parent=%s and holiday_date between %s and %s""",
					(d, filters["from_date"], filters["to_date"]),
				),
			)
	return holiday_map


@frappe.whitelist()
def get_attendance_years():
	year_list = frappe.db.sql_list(
		"""select distinct YEAR(attendance_date) from tabAttendance ORDER BY YEAR(attendance_date) DESC"""
	)
	if not year_list:
		year_list = [getdate().year]

	return "\n".join(str(year) for year in year_list)