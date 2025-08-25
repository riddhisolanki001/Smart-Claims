import frappe

# Create customer
# api/method/smartclaims.api.create.create_company 
@frappe.whitelist(allow_guest=True)
def create_company(**kwargs):
    try:
        company_id = kwargs.get("company_id")
        if not company_id:
            return {"status": "failed", "error": "Company ID is required"}

        # Build customer doc with mandatory field
        customer_doc = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": company_id  
        })

        # Map other fields from JSON
        meta = frappe.get_meta("Customer")
        for key, value in kwargs.items():
            if key == "company_id":
                continue 
            if meta.has_field(key):
                customer_doc.set(key, value)

        # Insert doc
        customer_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        return {"status": "success", "name": customer_doc.name}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "create_company error")
        return {"status": "failed", "error": str(e)}

# Create Supplier 
# api/method/smartclaims.api.create.create_provider
@frappe.whitelist(allow_guest=True)
def create_provider(**kwargs):
    try:
        # Use custom_provider_id if available, else supplier_name
        supplier_name = kwargs.get("custom_provider_id") 
        if not supplier_name:
            return {"status": "failed", "error": "Supplier ID is required"}

        # Build supplier doc with mandatory fields
        supplier_doc = frappe.get_doc({
            "doctype": "Supplier",
            "supplier_name": kwargs.get("custom_provider_id")
        })

        # Map other fields from JSON
        meta = frappe.get_meta("Supplier")
        for key, value in kwargs.items():
            if key in ("supplier_name"):
                continue  
            if meta.has_field(key):
                supplier_doc.set(key, value)

        # Insert doc
        supplier_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        return {"status": "success", "name": supplier_doc.name}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "create_supplier error")
        return {"status": "failed", "error": str(e)}