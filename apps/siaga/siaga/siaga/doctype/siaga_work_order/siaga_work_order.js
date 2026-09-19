// Copyright (c) 2026, SIAGA and contributors
// For license information, please see license.txt

const FAILURE_MODES = [
	"Bearing outer race",
	"Bearing inner race",
	"Bearing elemen gelinding",
	"Unbalance",
	"Misalignment",
	"Kelonggaran dudukan",
	"Seal bocor",
	"Impeller aus",
	"Motor",
	"Lainnya",
];

frappe.ui.form.on("SIAGA Work Order", {
	refresh(frm) {
		siaga_render_trigger(frm);
		if (frm.doc.docstatus !== 1) return;

		if (frm.doc.status === "Terbuka") {
			frm.add_custom_button(__("Mulai Dikerjakan"), () => {
				frm.call("start_work").then(() => frm.reload_doc());
			}).addClass("btn-primary");
		}

		if (["Terbuka", "Dikerjakan"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Selesai"), () => siaga_complete_dialog(frm));
		}

		if (frm.doc.health_score) {
			frm.add_custom_button(
				__("Skor Kesehatan Pemicu"),
				() => frappe.set_route("Form", "Health Score", frm.doc.health_score),
				__("Lihat")
			);
		}
		if (frm.doc.failure_log) {
			frm.add_custom_button(
				__("Catatan Kerusakan"),
				() => frappe.set_route("Form", "Failure Log", frm.doc.failure_log),
				__("Lihat")
			);
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

function siaga_complete_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Selesaikan work order"),
		fields: [
			{
				fieldname: "failure_mode",
				fieldtype: "Select",
				label: __("Apa yang sebenarnya rusak?"),
				options: FAILURE_MODES.join("\n"),
				reqd: 1,
				description: __("Ini jadi label pelatihan ulang, dibandingkan dengan tebakan sistem."),
			},
			{ fieldname: "failed_on", fieldtype: "Datetime", label: __("Waktu rusak ditemukan"), default: frappe.datetime.now_datetime(), reqd: 1 },
			{ fieldname: "root_cause", fieldtype: "Small Text", label: __("Akar masalah") },
			{
				fieldname: "component_replaced",
				fieldtype: "Check",
				label: __("Komponen diganti"),
				default: frm.doc.parts && frm.doc.parts.length ? 1 : 0,
			},
			{ fieldname: "notes", fieldtype: "Small Text", label: __("Catatan penyelesaian") },
		],
		primary_action_label: __("Selesai"),
		primary_action(values) {
			d.hide();
			frm.call("complete_work", values).then(() => frm.reload_doc());
		},
	});
	d.show();
}

function siaga_render_trigger(frm) {
	const field = frm.get_field("trigger_html");
	if (!field) return;
	const $w = $(field.wrapper).empty();
	if (!frm.doc.health_score) {
		if (frm.doc.trigger_source === "Otomatis") $w.html(`<div class="text-muted small">${__("Tanpa skor pemicu.")}</div>`);
		return;
	}
	frappe.db.get_value("Health Score", frm.doc.health_score, ["top_features", "score", "scored_at", "confidence", "has_projection", "days_to_threshold", "projection_low", "projection_high"]).then((r) => {
		const hs = r.message || {};
		let parsed = {};
		try {
			parsed = JSON.parse(hs.top_features || "{}");
		} catch (e) {
			parsed = {};
		}
		const devs = parsed.deviations || [];
		const rows = devs
			.map((d) => {
				const ratio = d.ratio == null ? "-" : d.ratio.toFixed(2) + "×";
				const cls = d.z > 0 ? "text-danger" : "text-muted";
				return `<tr><td><code>${d.feature}</code></td><td class="text-right">${d.value.toPrecision(3)}</td><td class="text-right">${d.baseline.toPrecision(3)}</td><td class="text-right"><b>${ratio}</b></td><td class="text-right ${cls}">${d.z > 0 ? "+" : ""}${d.z.toFixed(1)}</td></tr>`;
			})
			.join("");
		const proj = hs.has_projection
			? `${__("Proyeksi ke ambang")}: <b>${Number(hs.days_to_threshold).toFixed(1)} ${__("hari")}</b> (${Number(hs.projection_low).toFixed(1)}–${hs.projection_high ? Number(hs.projection_high).toFixed(1) : "∞"})`
			: __("Tidak ada tren turun yang berarti saat itu");
		$w.html(`
			<div class="small" style="margin-bottom:6px">
				${__("Skor")} <b>${Number(hs.score).toFixed(1)}</b> ${__("pada")} ${frappe.datetime.str_to_user(hs.scored_at)} ·
				${__("keyakinan")} ${Number(hs.confidence).toFixed(0)}% · ${__("gejala")}: <b>${parsed.symptom || "-"}</b><br>${proj}
			</div>
			<table class="table table-bordered table-sm small" style="margin-bottom:0">
				<thead><tr><th>${__("Ciri")}</th><th class="text-right">${__("Nilai")}</th><th class="text-right">${__("Baseline")}</th><th class="text-right">${__("Kelipatan")}</th><th class="text-right">z</th></tr></thead>
				<tbody>${rows || `<tr><td colspan="5" class="text-muted">${__("Tidak ada rincian")}</td></tr>`}</tbody>
			</table>`);
	});
}
