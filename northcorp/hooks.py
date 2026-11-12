from . import __version__ as app_version

app_name = "northcorp"
app_title = "northcorp"
app_publisher = "Shahzad Naser"
app_description = "northcorp"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "shahzadnaser1122@gmail.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/northcorp/css/northcorp.css"
app_include_js = "/assets/northcorp/js/northcorp.js?1.0.1"

# include js, css files in header of web template
# web_include_css = "/assets/northcorp/css/northcorp.css"
# web_include_js = "/assets/northcorp/js/northcorp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "northcorp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "northcorp.install.before_install"
# after_install = "northcorp.install.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "northcorp.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Insurance Policy: project teams only see policies linked to a project (Finance sees all)
permission_query_conditions = {
	"Insurance Policy": "northcorp.modules.insurance.policy_query_conditions",
}

has_permission = {
	"Insurance Policy": "northcorp.modules.insurance.policy_has_permission",
}

# Insurance records on the Project's Connections tab
override_doctype_dashboards = {
	"Project": "northcorp.modules.insurance.project_dashboard",
}

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Payroll Entry": "northcorp.modules.payroll_entry.CustomPayrollEntry",
	"Salary Slip": "northcorp.modules.salary_slip.CustomSalarySlip",
	"Salary Structure Assignment": "northcorp.modules.salary_structure_assignment.CustomSalaryStructureAssignment",
	"Expense Claim": "northcorp.modules.expense_claim.CustomExpenseClaim",
	"Email Digest": "northcorp.modules.email_digest.CustomEmailDigest",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Salary Slip":{
		"before_save" :  "northcorp.modules.salary_slip.before_save",
	},
   	"Salary Structure Assignment":{
		"before_save" :  "northcorp.modules.salary_structure_assignment.before_save"
	},
	"Attendance":{
		"before_submit":"northcorp.modules.attendance.before_submit",
	},
	# Auto Purchase Receipt for PO-linked service items once the invoice is fully approved,
	# and cancelled again with the invoice
	"Purchase Invoice":{
		"on_update_after_submit":"northcorp.modules.purchase_invoice.on_update_after_submit",
		"before_cancel":"northcorp.modules.purchase_invoice.before_cancel",
	}
}

# Include expense_claim_party_details in the Expense Claim outstanding amount used by
# Payment Entry and Journal Entry (see northcorp.modules.expense_claim)
before_request = ["northcorp.modules.expense_claim.apply_outstanding_amount_patch"]
before_job = ["northcorp.modules.expense_claim.apply_outstanding_amount_patch"]

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		# Monday 08:00 - Items Below Safety Stock weekly email (replaces the Server Script of the same name)
		"0 8 * * 1": [
			"northcorp.tasks.send_items_below_safety_stock_email",
		],
		# Daily 07:30 - insurance expiry / premium / extension / subcontractor certificate alerts
		"30 7 * * *": [
			"northcorp.modules.insurance.send_insurance_alerts",
		],
	},
}

# scheduler_events = {
# 	"all": [
# 		"northcorp.tasks.all"
# 	],
# 	"daily": [
# 		"northcorp.tasks.daily"
# 	],
# 	"hourly": [
# 		"northcorp.tasks.hourly"
# 	],
# 	"weekly": [
# 		"northcorp.tasks.weekly"
# 	]
# 	"monthly": [
# 		"northcorp.tasks.monthly"
# 	]
# }

# Testing
# -------

# before_tests = "northcorp.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "northcorp.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "northcorp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]


# User Data Protection
# --------------------

user_data_fields = [
	{
		"doctype": "{doctype_1}",
		"filter_by": "{filter_by}",
		"redact_fields": ["{field_1}", "{field_2}"],
		"partial": 1,
	},
	{
		"doctype": "{doctype_2}",
		"filter_by": "{filter_by}",
		"partial": 1,
	},
	{
		"doctype": "{doctype_3}",
		"strict": False,
	},
	{
		"doctype": "{doctype_4}"
	}
]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"northcorp.auth.validate"
# ]


# Everything customised in the ERPNext UI is exported here so GitHub holds the full system.
# On the server: bench --site <site> export-fixtures --app northcorp  (writes northcorp/fixtures/*.json)
# bench migrate imports these files back and OVERWRITES UI edits of the same records,
# so from now on change these through GitHub (or export right after a UI edit).
# User-saved Report Builder / Custom Report views and Auto Email Reports stay in the database.
fixtures = [
    "Custom Field",
    "Property Setter",
    "Client Script",
    {"doctype": "Server Script", "filters": [["name", "not like", "%TEST%"]]},
    "Workflow",
    "Workflow State",
    "Workflow Action Master",
    {"doctype": "Notification", "filters": [["is_standard", "=", 0]]},
    {"doctype": "Print Format", "filters": [["standard", "=", "No"]]},
    {"doctype": "Report", "filters": [
        ["is_standard", "=", "No"],
        ["report_type", "in", ["Script Report", "Query Report"]],
    ]},
    "Email Template",
    "Letter Head",
    {"doctype": "DocType", "filters": [["custom", "=", 1]]},
]

# from erpnext.payroll.doctype.salary_slip.salary_slip import SalarySlip
# from northcorp.modules.project import set_project_status

# SalarySlip.get_data_for_eval = get_data_for_eval


override_whitelisted_methods = {
	'erpnext.projects.doctype.project.project.set_project_status' : 'northcorp.modules.project.set_project_status'
}
