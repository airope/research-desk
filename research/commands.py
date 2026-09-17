"""Research commands: validated transitions independent of HTTP rendering."""

import uuid
from dataclasses import dataclass

from django.db import transaction

from .jobs import event
from .limits import admit_job
from .reviews import fingerprint


@dataclass
class CommandError(Exception):
    message: str
    bad_request: bool = False

    def __str__(self):
        return self.message


@transaction.atomic
def apply_command(dossier, user, data, capability):
    """Lock the owned dossier and validate against its current persisted state."""
    from .models import Dossier

    if dossier.owner_id != user.pk:
        raise CommandError("Dossier does not belong to this user", bad_request=True)
    dossier = Dossier.objects.select_for_update().get(pk=dossier.pk, owner_id=user.pk)
    command = data.get("action")
    running = dossier.status in {"queued", "running"}
    if command == "stop" and running:
        dossier.run_id = uuid.uuid4()
        dossier.status = "cancelled"
        if dossier.stage == "investigate":
            dossier.investigation["stop_reason"] = "Stopped by you."
            for step in dossier.investigation.get("steps", []):
                if step.get("status") == "running":
                    step["status"] = "cancelled"
        dossier.events.append(
            event(
                "Stopped by you. Any in-flight model request may finish, but its result will not be published."
            )
        )
    elif running:
        raise CommandError("Research is already running. Stop it before making changes.")
    elif command == "select":
        paper_id = data.get("paper_id")
        if paper_id not in {p["id"] for p in dossier.papers}:
            raise CommandError("Unknown paper", bad_request=True)
        selected = set(dossier.selected)
        if data.get("selected") == "1":
            selected.add(paper_id)
        else:
            selected.discard(paper_id)
        dossier.selected = [p["id"] for p in dossier.papers if p["id"] in selected]
    elif command == "review":
        if data.get("report_token") != fingerprint(dossier.report):
            raise CommandError("The report changed. Review its latest version before assessing it.")
        try:
            index = int(data.get("finding", "-1"))
        except ValueError:
            raise CommandError("Invalid finding", bad_request=True)
        verdict = data.get("verdict")
        if (
            index < 0
            or index >= len(dossier.report.get("findings", []))
            or verdict not in {"supported", "unsupported", "uncertain"}
        ):
            raise CommandError("Invalid assessment", bad_request=True)
        dossier.report.setdefault("reviews", {})[str(index)] = {
            "verdict": verdict,
            "note": data.get("note", "")[:1000],
            "actor": user.get_username(),
            "at": event("")["at"],
        }
    elif command in {"start", "retry", "regenerate", "fulltext", "followup", "investigate"}:
        if command == "start":
            queries = [q.strip() for q in data.get("queries", "").splitlines() if q.strip()]
            if not 1 <= len(queries) <= 3 or any(
                len(q) > 400 or any(ord(c) < 32 for c in q) for q in queries
            ):
                raise CommandError("Enter 1–3 queries, at most 400 characters each.")
            dossier.plan = {
                "scope": data.get("scope", dossier.question)[:2000],
                "queries": queries,
            }
            if dossier.report:
                dossier.versions = [
                    *dossier.versions,
                    {
                        "report": dossier.report,
                        "focus": dossier.report_focus,
                        "papers": dossier.report_papers or dossier.papers,
                        "selected": dossier.report_selected,
                    },
                ][-10:]
            dossier.report, dossier.report_selected, dossier.report_papers = {}, [], []
            dossier.papers, dossier.selected = [], []
            dossier.focus, dossier.report_focus = "", ""
            dossier.stage = "search"
        elif command in {"fulltext", "followup", "investigate"}:
            if not dossier.selected:
                raise CommandError("Select publications first.")
            if command in {"followup", "investigate"}:
                focus = data.get("focus", "").strip()
                if not 10 <= len(focus) <= 1500:
                    raise CommandError("Enter a follow-up question of 10–1500 characters.")
                dossier.focus = focus
            if command == "fulltext":
                dossier.use_fulltext = True
            dossier.stage = (
                "investigate"
                if command == "investigate"
                else "fulltext"
                if dossier.use_fulltext
                else "synthesize"
            )
            if command == "investigate":
                dossier.investigation = {}
        elif command == "regenerate":
            if not dossier.selected:
                raise CommandError("Include at least one paper first.")
            dossier.stage = "synthesize"
        else:
            dossier.stage = (
                "investigate"
                if dossier.stage == "investigate"
                else "synthesize"
                if dossier.papers
                else "search"
                if dossier.plan.get("queries")
                else "plan"
            )
        if dossier.stage != "search":
            available, message = capability(user)
            if not available:
                raise CommandError(message)
        admit_job(user.pk)
        dossier.status, dossier.error, dossier.run_id = "queued", "", uuid.uuid4()
        dossier.events.append(event("Queued for " + dossier.stage + "."))
    else:
        raise CommandError("Unknown action", bad_request=True)
    dossier.events = dossier.events[-100:]
    dossier.save()
    return command
