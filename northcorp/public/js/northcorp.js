frappe.ui.form.on('*', {
    setup: function(frm) {
        apply_project_filter(frm);
    },
    onload: function(frm) {
        console.log(frm.doctype);
        console.log("========onload1==========")
        setTimeout(() => {
            apply_project_filter(frm);
            console.log("========onload2==========")
            }, 4000
        );
    }
});
console.log("========northcorp==========")

function apply_project_filter(frm) {

    // ---- Main DocType ----
    if (frm.fields_dict.project) {
        frm.set_query("project", function() {
            return {
                filters: {
                }
            };
        });
    }

    // ---- Child Tables ----
    (frm.meta.fields || []).forEach(df => {
        if (df.fieldtype === "Table" && frm.fields_dict[df.fieldname]) {

            let grid = frm.fields_dict[df.fieldname].grid;

            if (grid && grid.get_field("project")) {
                grid.get_field("project").get_query = function(doc, cdt, cdn) {
                    return {
                        filters: {
                        }
                    };
                };
            }
        }
    });
}