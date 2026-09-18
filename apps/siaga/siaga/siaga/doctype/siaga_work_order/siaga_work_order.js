// Copyright (c) 2026, SIAGA and contributors
// For license information, please see license.txt

frappe.ui.form.on("SIAGA Work Order", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		if (frm.doc.status === "Terbuka") {
			frm.add_custom_button(__("Mulai Dikerjakan"), () => {
				frm.call("start_work").then(() => frm.reload_doc());
			}).addClass("btn-primary");
		}

		if (["Terbuka", "Dikerjakan"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Selesai"), () => {
				frappe.prompt(
					{
						fieldname: "notes",
						fieldtype: "Small Text",
						label: __("Catatan penyelesaian"),
					},
					(values) => {
						frm.call("complete_work", { notes: values.notes }).then(() => frm.reload_doc());
					},
					__("Selesaikan work order"),
					__("Selesai")
				);
			});
		}

		if (frm.doc.material_request) {
			frm.add_custom_button(
				__("Material Request"),
				() => frappe.set_route("Form", "Material Request", frm.doc.material_request),
				__("Lihat")
			);
		}
		frm.add_custom_button(
			__("Reservasi Part"),
			() => frappe.set_route("List", "Part Reservation", { work_order: frm.doc.name }),
			__("Lihat")
		);
	},

	asset(frm) {
		// Gudang sumber ikut lokasi aset kalau ada gudang dengan nama sama.
		if (!frm.doc.asset || frm.doc.warehouse) return;
		frappe.db.get_value("Asset", frm.doc.asset, "location").then((r) => {
			if (!r.message || !r.message.location) return;
			frappe.db.get_list("Warehouse", { filters: { warehouse_name: ["like", "%" + r.message.location + "%"] }, limit: 1 })
				.then((rows) => rows.length && frm.set_value("warehouse", rows[0].name));
		});
	},
});

frappe.ui.form.on("SIAGA Work Order Part", {
	item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.warehouse && frm.doc.warehouse) {
			frappe.model.set_value(cdt, cdn, "warehouse", frm.doc.warehouse);
		}
	},
});
