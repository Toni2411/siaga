// Copyright (c) 2026, SIAGA and contributors
// For license information, please see license.txt

frappe.ui.form.on("Asset Monitoring Profile", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (["Dipantau", "Ditangguhkan"].includes(frm.doc.monitoring_status)) {
			frm.add_custom_button(__("Kumpulkan Baseline Ulang"), () => {
				frappe.confirm(
					__("Model unit ini akan dibuang dan dilatih ulang dari data sehat sejak sekarang. Lakukan setelah komponen diganti. Lanjutkan?"),
					() => frm.call("restart_baseline").then(() => frm.reload_doc())
				);
			});
		}
		if (frm.doc.last_auto_work_order) {
			frm.add_custom_button(
				__("Work Order Otomatis Terakhir"),
				() => frappe.set_route("Form", "SIAGA Work Order", frm.doc.last_auto_work_order),
				__("Lihat")
			);
		}
		frm.add_custom_button(__("Aset"), () => frappe.set_route("Form", "Asset", frm.doc.asset), __("Lihat"));
	},
});
