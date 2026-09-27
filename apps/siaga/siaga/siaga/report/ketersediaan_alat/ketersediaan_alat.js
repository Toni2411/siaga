// Copyright (c) 2026, SIAGA and contributors
// For license information, please see license.txt

frappe.query_reports["Ketersediaan Alat"] = {
	filters: [
		{
			fieldname: "from_date", label: __("Dari"), fieldtype: "Datetime", reqd: 1,
			default: frappe.datetime.add_days(frappe.datetime.now_datetime(), -7),
		},
		{ fieldname: "to_date", label: __("Sampai"), fieldtype: "Datetime", reqd: 1, default: frappe.datetime.now_datetime() },
		{ fieldname: "asset", label: __("Aset"), fieldtype: "Link", options: "Asset" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		// Ambang warna mengikuti kebiasaan kontraktor tambang: PA 85%, UA 80%.
		const limits = { pa: 85, ua: 80, ma: 85 };
		if (data && column.fieldname in limits && data[column.fieldname] !== null) {
			const color = data[column.fieldname] >= limits[column.fieldname] ? "var(--green-600)" : "var(--red-500)";
			value = `<span style="color:${color};font-weight:600">${value}</span>`;
		}
		return value;
	},
};
