// Copyright (c) 2026, SIAGA and contributors
// For license information, please see license.txt

frappe.ui.form.on("Telegram Chat", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.status === "Menunggu tautan") {
			frm.dashboard.set_headline(
				__("Minta pengguna mengirim <b>/mulai {0}</b> ke bot Telegram SIAGA.", [frm.doc.link_code])
			);
		}
		frm.add_custom_button(__("Putuskan & kode baru"), () => {
			frappe.confirm(__("Chat yang tertaut akan diputus. Lanjutkan?"), () => {
				frm.call("reset_link").then(() => frm.reload_doc());
			});
		});
	},
});
