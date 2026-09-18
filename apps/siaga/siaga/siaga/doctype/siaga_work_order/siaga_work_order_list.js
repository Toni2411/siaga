// Indikator daftar mengikuti status kerja, bukan docstatus. Planner perlu
// melihat mana yang masih terbuka tanpa membuka satu per satu.

frappe.listview_settings["SIAGA Work Order"] = {
	add_fields: ["status", "priority"],
	get_indicator(doc) {
		const color = {
			Draft: "gray",
			Terbuka: "orange",
			Dikerjakan: "blue",
			Selesai: "green",
			Dibatalkan: "red",
		}[doc.status] || "gray";
		return [__(doc.status), color, "status,=," + doc.status];
	},
};
