// Copyright (c) 2022, Shahzad Naser and contributors
// For license information, please see license.txt

frappe.ui.form.on('Project Wise Timesheet', {
	refresh: function(frm) {
		frm.set_query('default_project', function () {
			return {
			  filters: {
				  "status": ["IN", ["Open", "Defect Liability Period"]]
			  }
			  
		  }
		});
		frm.set_query('project','employees', function () {
			return {
			  filters: {
				  "status": ["IN", ["Open", "Defect Liability Period"]]
			  }
			  
		  }
		});
  
	},
	get_employees: function (frm) {
		return frappe.call({
			doc: frm.doc,
			method: 'fill_employees',
		}).then(r => {
			if (r.docs && r.docs[0].employees) {
				frm.employees = r.docs[0].employees;
				frm.dirty();
				frm.save();
				frm.refresh();
			}
		});
	}
});

frappe.ui.form.on('Employee Timesheet', {
	start_time: function(frm, cdt, cdn) {
		let d = locals[cdt][cdn];

		if(d.start_time && d.end_time){
			let hours = calculate_timediff_hours(d.start_time , d.end_time);
			console.log(d.start_time , d.end_time, hours);
			frappe.model.set_value(cdt, cdn, "working_hours",hours);
			refresh_field("employees");
		}
	},
	end_time: function(frm, cdt, cdn) {
		let d = locals[cdt][cdn];
		if(d.start_time && d.end_time){
			let hours = calculate_timediff_hours(d.start_time , d.end_time);
			console.log(d.start_time , d.end_time, hours);
			frappe.model.set_value(cdt, cdn, "working_hours",hours);
			refresh_field("employees");
		}
	},
	attendance_date: function(frm, cdt, cdn) {
		let d = locals[cdt][cdn];
		if(d.attendance_date){
			frappe.model.set_value(cdt, cdn, "day",moment(d.attendance_date).format('dddd'));
			refresh_field("employees");
		}
	}
});

function calculate_timediff_hours(start_time, end_time){
	let diff_hours = 0;
	if (start_time && end_time){
		let duration = moment.duration(moment(end_time,"HH:mm:ss").diff(moment(start_time,"HH:mm:ss")));
		diff_hours = duration.asHours().toFixed(2);
	}
	return diff_hours;
}