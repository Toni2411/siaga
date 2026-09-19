// Copyright (c) 2026, SIAGA and contributors
// For license information, please see license.txt

frappe.query_reports["Lead Time Deteksi"] = {
	filters: [
		{ fieldname: "asset", label: __("Aset"), fieldtype: "Link", options: "Asset" },
		{ fieldname: "from_date", label: __("Rusak Sejak"), fieldtype: "Date" },
	],
};
