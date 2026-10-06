"""The Campus Customs agent team: Boss plus four specialists."""

from agents import accounting, boss, customer_service, facilities, inventory

ROSTER = {m.NAME: m for m in (boss, inventory, accounting, facilities, customer_service)}
