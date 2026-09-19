// Grafik tren kondisi di form Asset bawaan ERPNext.
// Data dibaca dari TimescaleDB lewat siaga.api.timeseries, bukan dari MariaDB.

frappe.ui.form.on("Asset", {
	refresh(frm) {
		if (frm.is_new()) return;
		siaga_render_trend(frm);
	},
});

const SIAGA_RANGES = [
	{ label: "24 jam", hours: 24 },
	{ label: "7 hari", hours: 24 * 7 },
	{ label: "30 hari", hours: 24 * 30 },
];

function siaga_render_trend(frm) {
	const field = frm.get_field("siaga_trend");
	if (!field) return;
	const $wrap = $(field.wrapper).empty();

	frappe.db.get_value("Asset Monitoring Profile", { asset: frm.doc.name }, ["data_source_id", "monitoring_status"]).then((r) => {
		const profile = r.message;
		if (!profile || !profile.data_source_id) {
			$wrap.html(`<div class="text-muted small">${__("Belum ada profil pemantauan untuk aset ini.")}</div>`);
			return;
		}

		const $toolbar = $(`
			<div class="siaga-trend-toolbar" style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap">
				<span class="small text-muted">${__("Sumber")}: <b>${profile.data_source_id}</b> · ${profile.monitoring_status}</span>
				<span style="flex:1"></span>
				<div class="btn-group btn-group-sm" role="group"></div>
			</div>`);
		const $health = $(`<div class="siaga-health-chart"></div>`);
		const $chart = $(`<div class="siaga-trend-chart" style="margin-top:12px"></div>`);
		const $latest = $(`<div class="small text-muted" style="margin-top:6px"></div>`);
		$wrap.append($toolbar, $health, $chart, $latest);

		const $group = $toolbar.find(".btn-group");
		let current = frm.__siaga_hours || 24 * 7;
		SIAGA_RANGES.forEach((rg) => {
			const $b = $(`<button type="button" class="btn btn-default btn-xs">${rg.label}</button>`);
			if (rg.hours === current) $b.addClass("btn-primary");
			$b.on("click", () => {
				frm.__siaga_hours = rg.hours;
				siaga_render_trend(frm);
			});
			$group.append($b);
		});

		frappe.call({
			method: "siaga.api.timeseries.get_health",
			args: { asset: frm.doc.name, hours: current },
		}).then((res) => {
			const d = res.message;
			if (!d.scores.length) {
				$health.html(`<div class="text-muted small">${__("Belum ada skor kesehatan. Status: ")}${d.profile.monitoring_status || "-"}</div>`);
				return;
			}
			const markers = [];
			if (d.thresholds.threshold_trigger) markers.push({ label: __("pemicu"), value: d.thresholds.threshold_trigger, options: { labelPos: "left" } });
			if (d.thresholds.threshold_recover) markers.push({ label: __("pulih"), value: d.thresholds.threshold_recover, options: { labelPos: "left" } });
			const alarm = d.profile.alarm_state === "Alarm"
				? ` · <span class="indicator-pill red">${__("Alarm")} ${d.profile.last_auto_work_order || ""}</span>`
				: ` · <span class="indicator-pill green">${__("Normal")}</span>`;
			$toolbar.find(".small").append(alarm);
			new frappe.Chart($health[0], {
				title: __("Skor kesehatan (0–100)"),
				data: { labels: d.labels, datasets: [{ name: __("skor"), values: d.scores }], yMarkers: markers },
				type: "line",
				height: 200,
				colors: ["#16a34a"],
				lineOptions: { hideDots: 1, regionFill: 1 },
				axisOptions: { xIsSeries: 1, xAxisMode: "tick" },
				tooltipOptions: { formatTooltipY: (v) => (v == null ? "-" : v.toFixed(1)) },
			});
		});

		frappe.call({
			method: "siaga.api.timeseries.get_trend",
			args: { asset: frm.doc.name, hours: current, normalize: 1 },
		}).then((res) => {
			const data = res.message;
			if (!data.labels.length) {
				$chart.html(`<div class="text-muted small">${__("Belum ada data dalam rentang ini.")}</div>`);
				return;
			}
			new frappe.Chart($chart[0], {
				title: __("Kelipatan terhadap baseline awal jendela"),
				data: { labels: data.labels, datasets: data.datasets },
				type: "line",
				height: 260,
				colors: ["#2490ef", "#e24c4c", "#f5a623", "#7c4dff"],
				lineOptions: { hideDots: 1, regionFill: 0 },
				axisOptions: { xIsSeries: 1, xAxisMode: "tick" },
				tooltipOptions: { formatTooltipY: (v) => (v == null ? "-" : v.toFixed(2) + "x") },
			});
		});

		frappe.call({ method: "siaga.api.timeseries.latest", args: { asset: frm.doc.name } }).then((res) => {
			const d = res.message;
			if (!d || !d.ts) return;
			const f = d.features || {};
			const fmt = (x) => (x == null ? "-" : Number(x).toFixed(4));
			$latest.html(
				`${__("Terakhir")}: ${frappe.datetime.str_to_user(d.ts.replace("T", " ").slice(0, 19))} · ` +
					`${__("kondisi")}: <b>${d.state}</b> · RMS ${fmt(f.vib_rms)} g · BPFO ${fmt(f.bpfo_energy)} · BPFI ${fmt(f.bpfi_energy)} · kurtosis ${fmt(f.vib_kurtosis)}`
			);
		});
	});
}
