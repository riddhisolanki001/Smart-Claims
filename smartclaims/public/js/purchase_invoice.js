frappe.ui.form.on('Purchase Invoice', {
    refresh(frm) {
		if (frm.doc.custom_invoice_type == "Medical Refunds"){
            frm.set_df_property('posting_date','label','Request Date');
            frm.refresh_field('posting_date');
        }
	}
});