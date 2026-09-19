# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Agen baca-saja: konteks dari izin user, jawaban dicatat, LLM tidak pernah dipanggil sungguhan."""

import frappe

from siaga import agent, telegram, telegram_bot
from siaga.tests.fixtures import SiagaTestCase, make_env, make_work_order, score

CHAT = "990009"


def message(text):
	return {"update_id": 1, "message": {"chat": {"id": int(CHAT), "type": "private"}, "from": {"first_name": "Uji"}, "text": text}}


class FakeLLM:
	model = "uji-llm"

	def __init__(self):
		self.prompts = []

	def chat(self, system, user):
		self.prompts.append((system, user))
		return "Jawaban uji: Pompa paling perlu perhatian adalah yang skornya terendah."


class TestAgent(SiagaTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.env = make_env("UJI-G")

	def setUp(self):
		super().setUp()
		self.llm = FakeLLM()
		self._client, self._config = agent.client, agent.config
		agent.client = lambda: self.llm
		agent.config = lambda: ("http://uji", "uji-llm")
		self.sent = []
		self._send = telegram.send
		telegram.send = lambda text, silent=False, chat_id=None, buttons=None: self.sent.append((chat_id, text)) or True
		frappe.set_user("Administrator")

	def tearDown(self):
		agent.client, agent.config = self._client, self._config
		telegram.send = self._send
		frappe.set_user("Administrator")
		super().tearDown()

	def test_context_reflects_current_state(self):
		e = self.env
		score(e.asset, 72, minutes_ago=1, projection=(5, 4, 9))
		frappe.db.set_value("Asset Monitoring Profile", e.profile, {"last_score": 72, "last_score_at": frappe.utils.now_datetime()})
		wo = make_work_order(e, component=e.component)
		ctx = agent.build_context()
		self.assertIn(e.asset_name, ctx)
		self.assertIn("skor 72", ctx)
		self.assertIn("proyeksi ke ambang ~5.0 hari", ctx)
		self.assertIn(wo.name, ctx)
		self.assertIn(e.item, ctx)
		self.assertIn("Riwayat kerusakan", ctx)

	def test_ask_uses_context_and_logs_query(self):
		e = self.env
		result = agent.ask("unit mana yang paling perlu perhatian?")
		self.assertIn("Jawaban uji", result["answer"])
		self.assertEqual(result["model"], "uji-llm")
		system, prompt = self.llm.prompts[-1]
		self.assertIn("HANYA dari data", system)
		self.assertIn(e.asset_name, prompt)
		self.assertTrue(prompt.rstrip().endswith("unit mana yang paling perlu perhatian?"))

		log = frappe.get_doc("Agent Query", result["query"])
		self.assertEqual((log.status, log.channel, log.user), ("Selesai", "API", "Administrator"))
		self.assertEqual(log.question, "unit mana yang paling perlu perhatian?")
		self.assertIn("Jawaban uji", log.answer)
		self.assertEqual(log.context_chars, result["context_chars"])

	def test_empty_or_too_long_question_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			agent.ask("   ")
		with self.assertRaises(frappe.ValidationError):
			agent.ask("x" * (agent.MAX_QUESTION + 1))
		self.assertEqual(self.llm.prompts, [])

	def test_disabled_when_no_url(self):
		agent.config = lambda: (None, "apa saja")
		agent.client = self._client
		self.assertFalse(agent.enabled())
		with self.assertRaises(frappe.ValidationError):
			agent.ask("halo")

	def test_context_obeys_reading_permissions_of_asking_user(self):
		user = "tamu-uji@siaga.local"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "Tamu Uji", "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			agent.build_context()

	def test_telegram_free_text_is_answered_in_background_as_linked_user(self):
		chat = frappe.get_doc({"doctype": "Telegram Chat", "user": "Administrator"}).insert(ignore_permissions=True)
		telegram_bot.handle_update(message("/mulai %s" % chat.link_code))
		self.sent.clear()

		# frappe.enqueue berjalan langsung saat in_test, jadi jawabannya sudah terkirim di sini.
		telegram_bot.handle_update(message("berapa work order yang terbuka?"))
		texts = [t for _, t in self.sent]
		self.assertTrue(any("Sebentar" in t for t in texts))
		self.assertTrue(any("Jawaban uji" in t and "baca-saja" in t for t in texts))
		log = frappe.get_last_doc("Agent Query")
		self.assertEqual((log.channel, log.chat_id, log.user), ("Telegram", CHAT, "Administrator"))

	def test_markdown_from_model_becomes_telegram_html(self):
		out = agent.to_telegram_html("## Ringkas\n**WO-1** & `x<y` **tebal**")
		self.assertEqual(out, "Ringkas\n<b>WO-1</b> &amp; <code>x&lt;y</code> <b>tebal</b>")

	def test_telegram_tanya_when_disabled_explains(self):
		agent.config = lambda: (None, "x")
		chat = frappe.get_doc({"doctype": "Telegram Chat", "user": "Administrator"}).insert(ignore_permissions=True)
		telegram_bot.handle_update(message("/mulai %s" % chat.link_code))
		telegram_bot.handle_update(message("/tanya ada apa?"))
		self.assertIn("tidak aktif", self.sent[-1][1])
		self.assertEqual(self.llm.prompts, [])
