"""Workflow shapes for the board-profile tests, in the form Jira.project_statuses returns them.

The status names and Jira categories come from the 2026-10-09 survey of the real Jira: GDNC and OYP file a «Done» under
in progress, BDBDESK has four «done» statuses, FDQ has a «Finalizado con error», UA's Tarea has its own workflow, and
a few projects hold two statuses with the same name. The groupings are simplified and every id is made up."""
from __future__ import annotations


def status(ident, name, category) -> dict:
    return {"id": str(ident), "name": name, "category": category}


GDNC = [{"types": ["Hallazgo"], "statuses": [
    status(20, "Abierto", "todo"), status(21, "En análisis", "in_progress"), status(22, "Done", "in_progress"),
    status(23, "Descartado", "done"), status(24, "Bloqueado", "in_progress"), status(25, "ON HOLD", "in_progress")]}]

BDBDESK = [{"types": ["Solicitud"], "statuses": [
    status(30, "Pendiente", "todo"), status(31, "En curso", "in_progress"), status(32, "Finalizado", "done"),
    status(33, "Resuelto", "done"), status(34, "Cancelado", "done"), status(35, "Implementado", "done")]}]

FDQ = [{"types": ["Tarea"], "statuses": [
    status(40, "To Do", "todo"), status(41, "Done", "done"), status(42, "Finalizado", "done"),
    status(43, "Finalizado con error", "done"), status(44, "Listo para entrega", "in_progress")]}]

UA = [{"types": ["Historia", "Error", "Epic", "Subtask"], "statuses": [
    status(1, "To Do", "todo"), status(2, "In Progress", "in_progress"), status(3, "ON HOLD", "in_progress"),
    status(4, "Done", "done")]},
    {"types": ["Tarea"], "statuses": [
        status(1, "To Do", "todo"), status(2, "In Progress", "in_progress"), status(5, "AWAITING APPROVAL", "in_progress"),
        status(6, "Approved", "in_progress"), status(7, "RELEASED", "done"), status(8, "NOT APPROVED", "done")]}]

PEHD = [{"types": ["Epic", "Tarea", "Story", "Solicitud"], "statuses": [
    status(50, "To Do", "todo"), status(51, "In Progress", "in_progress"), status(52, "Done", "done")]}]

SAME_NAME = [{"types": ["Tarea"], "statuses": [
    status(60, "To Do", "todo"), status(61, "en ejecucion", "in_progress"), status(62, "En ejecución", "in_progress"),
    status(63, "Done", "done")]}]
