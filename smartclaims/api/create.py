import frappe
@frappe.whitelist(allow_guest=True)
def create_company(**kwargs):
    try:
        company_data = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": kwargs.get("company_id"),
            "custom_company_name": kwargs.get("custom_company_name"),
        })
        company_data.insert(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "success", "name": company_data.name}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "create_company error")
        return {"status": "failed", "error": str(e)}

    