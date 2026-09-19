# Copyright (c) 2026, SIAGA and contributors
# For license information, please see license.txt

"""Pemetaan chat Telegram ke user ERPNext.

Planner membuat satu baris per user; sistem memberi kode tautan. Mekanik
mengirim `/mulai KODE` ke bot dari HP-nya, dan sejak itu tiap perintah dari
chat itu dijalankan sebagai user tersebut, dengan izin user tersebut.
"""

import secrets
import string

import frappe
from frappe import _
from frappe.model.document import Document

ALPHABET = string.ascii_uppercase + string.digits


def new_code(length=6):
	return "".join(secrets.choice(ALPHABET) for _ in range(length))


class TelegramChat(Document):
	def validate(self):
		if not self.link_code:
			self.link_code = new_code()
		if self.chat_id and self.status == "Menunggu tautan":
			self.status = "Tertaut"
		if not self.chat_id and self.status == "Tertaut":
			frappe.throw(_("Chat ID kosong, status tidak bisa Tertaut"))

	@frappe.whitelist()
	def reset_link(self):
		"""Putuskan chat dan buat kode baru, misalnya kalau HP berganti."""
		self.chat_id = None
		self.telegram_name = None
		self.linked_on = None
		self.pending = None
		self.link_code = new_code()
		self.status = "Menunggu tautan"
		self.save()
		return self.link_code
