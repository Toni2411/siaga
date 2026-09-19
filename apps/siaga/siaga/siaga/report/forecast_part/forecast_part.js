// Copyright (c) 2026, SIAGA and contributors
// For license information, please see license.txt

frappe.query_reports["Forecast Part"] = {
	filters: [
		{ fieldname: "warehouse", label: __("Gudang"), fieldtype: "Link", options: "Warehouse" },
		{
			fieldname: "horizon_days", label: __("Horizon (hari)"), fieldtype: "Int", default: 14,
			description: __("Kosong berarti memakai horizon tiap kelas alat"),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "advice" && data) {
			const color = data.advice.startsWith("Pesan") ? "red" : (data.advice === "Cukup" ? "green" : "orange");
			value = `<span class="indicator-pill ${color}">${data.advice}</span>`;
		}
		if (column.fieldname === "projected_after" && data && data.projected_after < 0) {
			value = `<span style="color:var(--red-500);font-weight:600">${value}</span>`;
		}
		return value;
	},
};
