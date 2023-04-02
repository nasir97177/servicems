// Copyright (c) 2022, Aakvatech Limited and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Service Job Card Detail"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"fieldtype": "Date",
			"label": __("From Date"),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"fieldtype": "Date",
			"label": __("To Date"),
			"reqd": 1
		},
		{
			"fieldname": "customer_view",
			"fieldtype": "Check",
			"label": __("Customer View")
		},
	]
};
