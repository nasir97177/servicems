# Copyright (c) 2021, Aakvatech Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.website.website_generator import WebsiteGenerator
from frappe import _
from frappe.utils import nowdate, nowtime, cint
import json


class ServiceJobCard(WebsiteGenerator):
    def validate(self):
        self.update_tables()
        self.set_parts_rate()
        self.set_totals()
        self.vaildate_complete()

    def before_submit(self):
        use_parts_entry = (
            frappe.get_value("Company Service Management Settings", "use_parts_entry")
            or 0
        )
        if use_parts_entry:
            self.create_parts_entry("before_submit")
        else:
            self.create_stock_entry("before_submit")
            self.create_invoice()

    def on_submit(self):
        if self.status != "Completed":
            frappe.throw(_("It is not allowed to submit if it is not completed"))

    def update_tables(self):
        for template in self.services:
            if not template.bypass_billable:
                template.is_billable = frappe.get_value(
                    "Service Template", template.service, "is_billable"
                )
            if not template.applied:
                template_doc = frappe.get_doc("Service Template", template.service)
                if template_doc.tasks:
                    for task in template_doc.tasks:
                        row = self.append("tasks", {})
                        row.task_name = task.task_name
                        row.template = template_doc.name

                if template_doc.parts:
                    for part in template_doc.parts:
                        row = self.append("parts", {})
                        row.item = part.item
                        row.qty = part.qty
                        row.rate = get_item_price(
                            part.item,
                            self.get_price_list(template_doc.price_list),
                            self.company,
                        )
                        row.is_billable = part.is_billable
                template.applied = 1

    def set_totals(self):
        self.service_charges = 0
        self.spares_cost = 0
        self.total = 0

        if self.services:
            for service in self.services:
                service.rate = get_item_price(
                    service.item, self.get_price_list(service.price_list), self.company
                )
                if service.is_billable:
                    self.service_charges += service.rate
        if self.parts:
            for part in self.parts:
                if part.is_billable:
                    self.spares_cost += part.rate * part.qty
        if self.supplied_parts:
            for supplied_part in self.supplied_parts:
                if supplied_part.is_billable:
                    self.spares_cost += supplied_part.rate * supplied_part.qty

        self.total = self.service_charges + self.spares_cost

    def set_parts_rate(self):
        price_list = self.get_price_list()
        for item in self.parts:
            if not item.rate:
                item.rate = get_item_price(item.item, price_list, self.company)

    # @frappe.whitelist()
    def create_parts_entry(self, type):
        if self.parts and len(self.parts) > 0:
            items = []
            for item in self.parts:
                if item.qty > 0:
                    items.append(
                        {
                            "item_code": item.item,
                            "qty": item.qty,
                        }
                    )

            if len(items) == 0:
                return

            doc = frappe.get_doc(
                dict(
                    doctype="Service Parts Entry",
                    posting_date=nowdate(),
                    posting_time=nowtime(),
                    company=self.company,
                    service_job_card=self.name,
                    items=items,
                ),
            )
            frappe.flags.ignore_account_permission = True
            doc.insert(ignore_permissions=True)
            doc.submit()
            frappe.msgprint(
                _("Service Parts Entry Created {0}").format(doc.name), alert=True
            )

            if doc.get("name"):
                left_parts = []
                for row in self.parts:
                    if row.qty > 0:
                        new_row = self.append("supplied_parts", {})
                        new_row.item = row.item
                        new_row.qty = row.qty
                        new_row.rate = row.rate
                        new_row.is_billable = row.is_billable
                        new_row.stock_entry = doc.name
                    else:
                        left_parts.append(row)
                self.parts = left_parts
                if type == "call":
                    self.save()

    @frappe.whitelist()
    def create_stock_entry(self, type):
        if self.parts and len(self.parts) > 0:
            workshop = frappe.get_doc("Service Workshop", self.workshop)
            items = []
            for item in self.parts:
                if item.qty > 0:
                    items.append(
                        {
                            "s_warehouse": workshop.parts_warehouse,
                            "t_warehouse": workshop.workshop_warehouse,
                            "item_code": item.item,
                            "qty": item.qty,
                            "uom": frappe.get_value("Item", item.item, "stock_uom"),
                        }
                    )

            if len(items) == 0:
                return

            doc = frappe.get_doc(
                dict(
                    doctype="Stock Entry",
                    posting_date=nowdate(),
                    posting_time=nowtime(),
                    stock_entry_type="Material Transfer",
                    purpose="Material Transfer",
                    company=self.company,
                    service_job_card=self.name,
                    from_warehouse=workshop.parts_warehouse,
                    to_warehouse=workshop.workshop_warehouse,
                    items=items,
                ),
            )
            frappe.flags.ignore_account_permission = True
            doc.insert(ignore_permissions=True)
            doc.submit()
            frappe.msgprint(_("Stock Entry Created {0}").format(doc.name), alert=True)

            if doc.get("name"):
                left_parts = []
                for row in self.parts:
                    if row.qty > 0:
                        new_row = self.append("supplied_parts", {})
                        new_row.item = row.item
                        new_row.qty = row.qty
                        new_row.rate = row.rate
                        new_row.is_billable = row.is_billable
                        new_row.stock_entry = doc.name
                    else:
                        left_parts.append(row)
                self.parts = left_parts
                if type == "call":
                    self.save()

    def create_invoice(self):
        if self.status != "Completed":
            return
        items = []
        workshop = frappe.get_doc("Service Workshop", self.workshop)
        if self.services and len(self.services) > 0:
            for item in self.services:
                if not item.is_billable:
                    continue

                items.append(
                    {
                        "item_code": item.item,
                        "qty": 1,
                        "uom": frappe.get_value("Item", item.item, "stock_uom"),
                        "warehouse": workshop.workshop_warehouse,
                        "rate": item.rate if item.is_billable else 0,
                    }
                )
        if self.supplied_parts and len(self.supplied_parts) > 0:
            for item in self.supplied_parts:
                if not item.is_billable or item.is_return or item.qty == 0:
                    continue

                items.append(
                    {
                        "item_code": item.item,
                        "qty": item.qty,
                        "uom": frappe.get_value("Item", item.item, "stock_uom"),
                        "warehouse": workshop.workshop_warehouse,
                        "rate": item.rate if item.is_billable else 0,
                    }
                )
            taxes = frappe.get_value(
                "Sales Taxes and Charges Template",
                {"company": self.company, "is_default": 1},
                ["name", "tax_category"],
                as_dict=1,
            )

            if len(items) == 0:
                return
            date = nowdate()
            doc = frappe.get_doc(
                dict(
                    doctype="Sales Invoice",
                    customer=self.customer,
                    posting_date=date,
                    due_date=date,
                    update_stock=1,
                    service_job_card=self.name,
                    company=self.company,
                    ignore_pricing_rule=1,
                    set_warehouse=workshop.workshop_warehouse,
                    items=items,
                    taxes_and_charges=taxes.name,
                    tax_category=taxes.tax_category,
                ),
            )
            frappe.flags.ignore_account_permission = True
            doc.set_taxes()
            doc.set_missing_values(for_validate=True)
            doc.flags.ignore_mandatory = True
            doc.calculate_taxes_and_totals()
            doc.insert(ignore_permissions=True)
            self.invoice = doc.name
            frappe.msgprint(_("Sales Invoice Created {0}").format(doc.name), alert=True)

    def vaildate_complete(self):
        if self.status != "Completed":
            return
        completed = True
        for task in self.tasks:
            if not task.completed:
                completed = False
        if not completed:
            frappe.throw(_("The Tasks is not Completed"))

    def get_price_list(self, template_price_list=None):
        price_list = frappe.get_value("Customer", self.customer, "default_price_list")
        if not price_list and template_price_list:
            price_list = template_price_list
        if not price_list:
            price_list = frappe.get_value(
                "Service Settings", "Service Settings", "price_list"
            )
        return price_list or ""


def get_item_price(item_code, price_list, company):
    price = 0
    company_currency = frappe.get_value("Company", company, "default_currency")
    item_prices_data = frappe.get_all(
        "Item Price",
        fields=["item_code", "price_list_rate", "currency"],
        filters={
            "price_list": price_list,
            "item_code": item_code,
            "currency": company_currency,
        },
        order_by="valid_from desc",
    )
    if len(item_prices_data):
        price = item_prices_data[0].price_list_rate or 0
    return price


@frappe.whitelist()
def get_selected_items(items):
    selected_items = json.loads(items)

    if selected_items:
        doc = frappe.get_doc(
            selected_items[0]["parenttype"], selected_items[0]["parent"]
        )
        source_doc = frappe.get_doc("Stock Entry", selected_items[0]["stock_entry"])

        new_doc = frappe.new_doc("Stock Entry")
        new_doc.company = source_doc.company
        new_doc.stock_entry_type = source_doc.stock_entry_type
        new_doc.purpose = source_doc.purpose
        new_doc.posting_date = nowdate()
        new_doc.posting_time = nowtime()
        new_doc.from_warehouse = source_doc.to_warehouse
        new_doc.to_warehouse = source_doc.from_warehouse
        new_doc.is_return = 1
        new_doc.service_job_card = doc.name

        for item in selected_items:
            if not item.get("qty_to_return"):
                frappe.throw(
                    _(
                        '<h4 class="text-center" style="background-color: yellow; font-weight: bold;">\
                    Can not process stock entry for empty quantity to return<h4>'
                    )
                )

            for entry in source_doc.items:
                if item.get("item") == entry.item_code:
                    new_doc.append(
                        "items",
                        {
                            "s_warehouse": entry.t_warehouse,
                            "t_warehouse": entry.s_warehouse,
                            "item_code": item.get("item"),
                            "item_name": entry.item_name,
                            "description": entry.description,
                            "item_group": entry.item_group,
                            "qty": item.get("qty_to_return"),
                            "transfer_qty": item.get("qty_to_return"),
                            "uom": entry.uom,
                            "stock_uom": entry.stock_uom,
                            "conversion_factor": entry.conversion_factor,
                            "expense_account": entry.expense_account,
                            "basic_rate": item.get("rate"),
                            "basic_amount": item.get("rate"),
                            "amount": item.get("rate"),
                            "cost_center": entry.cost_center,
                        },
                    )

        new_doc.save(ignore_permissions=True)
        new_doc.submit()
        if new_doc.get("name"):
            updated_supplied_parts(doc, selected_items, new_doc.get("name"))
            frappe.msgprint(
                "Stock Entry: {0} Created Successfully".format(
                    frappe.bold(new_doc.name)
                )
            )
        else:
            frappe.throw("Stock Entry was not created, try again")


def updated_supplied_parts(doc, selected_items, name):
    for row in doc.supplied_parts:
        if not row.is_billable:
            continue
        for d in selected_items:
            if row.item == d["item"]:
                row.qty_returned = d.get("qty_to_return")
                row.qty = cint(d.get("qty")) - cint(d.get("qty_to_return"))
                row.return_stock_enty = name
                if (cint(d.get("qty")) - cint(d.get("qty_to_return"))) == 0:
                    row.is_billable = 0
                    row.is_return = 1
    doc.save()
    doc.reload()


@frappe.whitelist()
def get_all_supplied_parts(job_card):
    return frappe.get_all("Supplied Parts", 
        filters={"parent": job_card, "is_billable": 1, "is_return": 0},
        fields=["idx", "item", "item_name", "qty", "rate", "stock_entry", "parent", "parenttype"],
        order_by = 'idx ASC',
        page_length=100
    )