# Copyright (c) 2026, SIAGA and contributors
# See license.txt

"""Bot Telegram: tautan chat, perintah, tombol, dan batas izin.

Pengiriman ke Telegram diganti dengan penampung, jadi tes hanya memeriksa
apa yang dikatakan bot dan apa yang berubah di ERPNext.
"""

import frappe

from siaga import telegram, telegram_bot
from siaga.tests.fixtures import SiagaTestCase, make_env, make_work_order, score

CHAT = "990001"


def message(text, chat_id=CHAT, update_id=1):
	return {"update_id": update_id, "message": {"chat": {"id": int(chat_id), "type": "private"},
	        "from": {"first_name": "Mekanik", "last_name": "Uji"}, "text": text}}


def press(data, chat_id=CHAT, update_id=2):
	return {"update_id": update_id, "callback_query": {"id": "cb-%s" % update_id, "from": {"first_name": "Mekanik"},
	        "message": {"chat": {"id": int(chat_id), "type": "private"}}, "data": data}}


class TestTelegramBot(SiagaTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env = make_env("UJI-T", stock_qty=3)
		cls.user = "mekanik-uji@siaga.local"
		if not frappe.db.exists("User", cls.user):
			frappe.get_doc({
				"doctype": "User", "email": cls.user, "first_name": "Mekanik Uji",
				"send_welcome_email": 0, "roles": [{"role": "Maintenance User"}, {"role": "Stock User"}],
			}).insert(ignore_permissions=True)

	def setUp(self):
		super().setUp()
		self.sent = []
		self.calls = []
		self._send, self._call = telegram.send, telegram.call
		telegram.send = lambda text, silent=False, chat_id=None, buttons=None: self.sent.append((chat_id, text, buttons)) or True
		telegram.call = lambda method, payload: self.calls.append((method, payload)) or {}
		frappe.set_user("Administrator")

	def tearDown(self):
		telegram.send, telegram.call = self._send, self._call
		frappe.set_user("Administrator")
		super().tearDown()
		# Peran yang diubah di dalam tes sudah digulung balik di DB; cache perannya belum.
		frappe.clear_cache(user=self.user)

	# ---- alat ----

	def handle(self, update):
		frappe.set_user("Administrator")  # relay: bot atau System Manager
		return telegram_bot.handle_update(update)

	def link_chat(self, chat_id=CHAT):
		doc = frappe.get_doc({"doctype": "Telegram Chat", "user": self.user}).insert(ignore_permissions=True)
		self.handle(message("/mulai %s" % doc.link_code.lower(), chat_id))
		doc.reload()
		return doc

	def last_text(self):
		return self.sent[-1][1]

	# ---- tes ----

	def test_split_command(self):
		self.assertEqual(telegram_bot.split_command("/mulai ABC123"), ("mulai", "ABC123"))
		self.assertEqual(telegram_bot.split_command("/wo@siaga_bot"), ("wo", ""))
		self.assertEqual(telegram_bot.split_command("  catatan bebas "), (None, "catatan bebas"))

	def test_unlinked_chat_gets_instructions_and_chat_id(self):
		self.handle(message("/wo"))
		self.assertIn("belum ditautkan", self.last_text())
		self.assertIn(CHAT, self.last_text())

	def test_link_with_code_then_wrong_code_then_relink_refused(self):
		doc = self.link_chat()
		self.assertEqual(doc.status, "Tertaut")
		self.assertEqual(doc.chat_id, CHAT)
		self.assertEqual(doc.telegram_name, "Mekanik Uji")
		self.assertIn("Tertaut sebagai", self.last_text())

		self.handle(message("/mulai XXXXXX", "990002"))
		self.assertIn("tidak dikenal", self.last_text())

		self.handle(message("/mulai %s" % doc.link_code))
		self.assertIn("sudah tertaut", self.last_text())

	def test_reset_link_issues_new_code(self):
		doc = self.link_chat()
		old = doc.link_code
		doc.reset_link()
		doc.reload()
		self.assertEqual(doc.status, "Menunggu tautan")
		self.assertIsNone(doc.chat_id)
		self.assertNotEqual(doc.link_code, old)

	def test_wo_lists_open_work_orders_with_buttons(self):
		self.link_chat()
		wo = make_work_order(self.env)
		self.handle(message("/wo"))
		chat_id, text, buttons = self.sent[-1]
		self.assertEqual(chat_id, CHAT)
		self.assertIn(wo.name, text)
		flat = [data for row in buttons for _, data in row]
		self.assertIn("wo:mulai:%s" % wo.name, flat)
		self.assertIn("wo:selesai:%s" % wo.name, flat)

	def test_button_flow_completes_work_order_as_linked_user(self):
		e = self.env
		self.link_chat()
		wo = make_work_order(e, component=e.component)

		self.handle(press("wo:mulai:%s" % wo.name, update_id=10))
		self.assertEqual(frappe.db.get_value("SIAGA Work Order", wo.name, "status"), "Dikerjakan")
		self.assertEqual(self.calls[-1][0], "answerCallbackQuery")

		self.handle(press("wo:selesai:%s" % wo.name, update_id=11))
		self.assertIn("Apa yang rusak", self.last_text())
		idx = telegram_bot.FAILURE_MODES.index("Bearing inner race")
		self.handle(press("wo:fm:%s:%d" % (wo.name, idx), update_id=12))
		self.assertIn("diganti?", self.last_text())
		self.handle(press("wo:cr:%s:1" % wo.name, update_id=13))
		self.assertIn("catatan", self.last_text().lower())
		self.assertTrue(frappe.db.get_value("Telegram Chat", {"chat_id": CHAT}, "pending"))

		self.handle(message("Bearing diganti, uji jalan normal"))
		wo.reload()
		self.assertEqual(wo.status, "Selesai")
		self.assertEqual(wo.completion_notes, "Bearing diganti, uji jalan normal")
		log = frappe.get_doc("Failure Log", wo.failure_log)
		self.assertEqual(log.failure_mode, "Bearing inner race")
		self.assertEqual(log.training_label, "bpfi")
		self.assertEqual(frappe.db.get_value("Asset Component", e.component, "status"), "Diganti")
		self.assertFalse(frappe.db.get_value("Telegram Chat", {"chat_id": CHAT}, "pending"))
		self.assertIn("Selesai", self.last_text())
		# Aksi berjalan sebagai user tertaut, bukan sebagai bot atau Administrator.
		self.assertEqual(wo.modified_by, self.user)

	def test_skip_notes_and_cancel(self):
		e = self.env
		self.link_chat()
		wo = make_work_order(e)
		self.handle(press("wo:selesai:%s" % wo.name, update_id=20))
		self.handle(press("wo:fm:%s:-" % wo.name, update_id=21))  # tanpa catatan kerusakan, tanpa komponen
		self.handle(message("/batal"))
		self.assertEqual(frappe.db.get_value("SIAGA Work Order", wo.name, "status"), "Terbuka")

		self.handle(press("wo:selesai:%s" % wo.name, update_id=22))
		self.handle(press("wo:fm:%s:-" % wo.name, update_id=23))
		self.handle(message("/lewati"))
		wo.reload()
		self.assertEqual(wo.status, "Selesai")
		self.assertFalse(wo.failure_log)

	def test_business_rule_rejection_is_relayed_and_rolled_back(self):
		self.link_chat()
		wo = make_work_order(self.env)
		wo.complete_work()
		self.handle(press("wo:mulai:%s" % wo.name, update_id=30))
		self.assertIn("⚠️", self.last_text())
		self.assertIn("Tidak bisa dari status", self.last_text())

	def test_user_without_write_permission_is_refused(self):
		self.link_chat()
		wo = make_work_order(self.env)
		# Cabut semua peran: user tertaut tidak lagi boleh menulis work order.
		user = frappe.get_doc("User", self.user)
		user.set("roles", [])
		user.save(ignore_permissions=True)
		frappe.clear_cache(user=self.user)
		self.handle(press("wo:mulai:%s" % wo.name, update_id=40))
		self.assertIn("Tidak punya izin", self.last_text())
		self.assertEqual(frappe.db.get_value("SIAGA Work Order", wo.name, "status"), "Terbuka")

	def test_relay_endpoint_requires_bot_or_system_manager(self):
		frappe.set_user(self.user)
		with self.assertRaises(frappe.PermissionError):
			telegram_bot.handle_update(message("/wo"))

	def test_unit_and_stok(self):
		e = self.env
		self.link_chat()
		score(e.asset, 88, minutes_ago=1)
		frappe.db.set_value("Asset Monitoring Profile", e.profile, {"last_score": 88, "last_score_at": frappe.utils.now_datetime()})
		self.handle(message("/unit"))
		self.assertIn(e.asset_name, self.last_text())
		self.assertIn("88", self.last_text())
		self.handle(message("/stok"))
		self.assertIn(e.item, self.last_text())
