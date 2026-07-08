"""Ocean.io CRM lead prospecting and enrichment scenario."""
from __future__ import annotations

import os

from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.rpc.errors import RpcError
from cap_qa_platform.scenarios.base import ScenarioRunResult, StepOutcome
from cap_qa_platform.scenarios.so_base import _StepFailed, unique_suffix

SCENARIO_NAME = "ocean_lead_enrichment"
REQUIRED_MODULES = ("cap_ocean_connector", "crm")
OCEAN_TAG_NAME = "Ocean"


class OceanLeadEnrichmentScenario:
    def __init__(self, no_cleanup: bool = False, **kwargs):
        self.no_cleanup = no_cleanup
        self.admin: OdooRPCClient | None = None
        self.suffix = unique_suffix()
        self.cleanup_tracker: list[tuple[str, int]] = []

    def bind_admin(self, admin: OdooRPCClient) -> None:
        self.admin = admin

    def _track(self, model: str, record_id: int) -> None:
        if not self.no_cleanup:
            self.cleanup_tracker.append((model, record_id))

    def _step(self, result: ScenarioRunResult, step: str, fn):
        try:
            value = fn()
            result.steps.append(StepOutcome(step=step, ok=True))
            return value
        except Exception as exc:
            result.steps.append(StepOutcome(step=step, ok=False, error=str(exc)))
            raise _StepFailed(step, str(exc)) from exc

    def run(self, rpc: OdooRPCClient, role_name: str) -> ScenarioRunResult:
        result = ScenarioRunResult(scenario=SCENARIO_NAME, role_name=role_name, success=False)
        if not self.admin:
            result.failed_step = "setup"
            result.error = "Admin client required."
            return result
        try:
            ctx = self._step(result, "assert_modules_installed", lambda: self._assert_modules(rpc))
            ctx["instance_id"] = self._step(
                result,
                "resolve_ocean_instance",
                lambda: self._resolve_ocean_instance(rpc),
            )
            ctx.update(
                self._step(
                    result,
                    "prospect_and_create_lead",
                    lambda: self._prospect_and_create_lead(rpc, ctx["instance_id"]),
                )
            )
            self._step(
                result,
                "assert_lead_from_ocean",
                lambda: self._assert_lead_from_ocean(rpc, ctx),
            )
            if ctx.get("from_live_search"):
                self._step(
                    result,
                    "enrich_lead_via_lookup",
                    lambda: self._enrich_lead_via_lookup(rpc, ctx),
                )
            else:
                result.steps.append(
                    StepOutcome(
                        step="enrich_lead_via_lookup_skipped",
                        ok=True,
                        error="Seeded prospect used — live Ocean lookup enrichment skipped.",
                    )
                )
            result.records = ctx
            result.success = True
        except _StepFailed as exc:
            result.failed_step = exc.step
            result.error = exc.message
        return result

    def cleanup_as_admin(self, admin: OdooRPCClient) -> None:
        for model, record_id in reversed(self.cleanup_tracker):
            try:
                admin.unlink(model, [record_id])
            except RpcError:
                pass
        self.cleanup_tracker.clear()

    def _assert_modules(self, rpc: OdooRPCClient) -> dict:
        missing = []
        for module in REQUIRED_MODULES:
            installed = rpc.search_count(
                "ir.module.module",
                [("name", "=", module), ("state", "=", "installed")],
            )
            if not installed:
                missing.append(module)
        if missing:
            raise AssertionError(f"Missing installed modules: {', '.join(missing)}")
        fields = rpc.fields_get("crm.lead", attributes=["type"])
        if "ocean_person_id" not in fields:
            raise AssertionError("crm.lead.ocean_person_id field not found.")
        return {}

    def _resolve_ocean_instance(self, rpc: OdooRPCClient) -> int:
        company_id = m2o_id(rpc.read("res.users", [rpc.uid], ["company_id"])[0]["company_id"])
        domain = [("active", "=", True)]
        if company_id:
            domain.append(("company_id", "=", company_id))
        instances = rpc.search_read("ocean.instance", domain, ["id", "name"], limit=1)
        if not instances:
            raise AssertionError(
                "No active Ocean.io instance configured for the test user's company."
            )
        return instances[0]["id"]

    def _prospect_and_create_lead(self, rpc: OdooRPCClient, instance_id: int) -> dict:
        prospect_id = rpc.create(
            "ocean.lead.prospect",
            {
                "instance_id": instance_id,
                "include_domains": os.environ.get("CAP_QA_OCEAN_SEARCH_DOMAIN", "odoo.com"),
                "size": 5,
                "people_per_company": 1,
            },
        )
        line_id: int | None = None
        ocean_person_id: str | None = None
        from_live_search = False

        try:
            rpc.call("ocean.lead.prospect", "action_search_prospects", [prospect_id])
            line_ids = rpc.search(
                "ocean.lead.prospect.line",
                [("prospect_id", "=", prospect_id), ("state", "=", "search")],
                limit=1,
            )
            if line_ids:
                line_id = line_ids[0]
                line = rpc.read(
                    "ocean.lead.prospect.line",
                    [line_id],
                    ["ocean_person_id", "first_name", "last_name", "organization_name", "email"],
                )[0]
                ocean_person_id = line.get("ocean_person_id")
                from_live_search = True
        except RpcError:
            pass

        if not line_id:
            line_id = self._seed_prospect_line(rpc, prospect_id)
            line = rpc.read(
                "ocean.lead.prospect.line",
                [line_id],
                ["ocean_person_id", "first_name", "last_name", "organization_name", "email"],
            )[0]
            ocean_person_id = line.get("ocean_person_id")

        lead_ref = rpc.call("ocean.lead.prospect.line", "action_create_crm_lead", [line_id])
        lead_id = m2o_id(lead_ref)
        if not lead_id:
            line = rpc.read("ocean.lead.prospect.line", [line_id], ["crm_lead_id"])[0]
            lead_id = m2o_id(line.get("crm_lead_id"))
        if not lead_id:
            raise AssertionError("action_create_crm_lead did not return a CRM lead.")

        self._track("crm.lead", lead_id)
        return {
            "prospect_id": prospect_id,
            "prospect_line_id": line_id,
            "lead_id": lead_id,
            "ocean_person_id": ocean_person_id,
            "expected_contact_name": " ".join(
                part
                for part in (line.get("first_name") or "", line.get("last_name") or "")
                if part
            ).strip(),
            "expected_partner_name": line.get("organization_name"),
            "expected_email": line.get("email"),
            "from_live_search": from_live_search,
        }

    def _seed_prospect_line(self, rpc: OdooRPCClient, prospect_id: int) -> int:
        ocean_person_id = f"capqa_{self.suffix}"
        email = f"capqa.{self.suffix}@example.com"
        line_id = rpc.create(
            "ocean.lead.prospect.line",
            {
                "prospect_id": prospect_id,
                "ocean_person_id": ocean_person_id,
                "first_name": "CAP",
                "last_name": f"QA{self.suffix[-6:]}",
                "name": f"CAP QA {self.suffix}",
                "title": "QA Engineer",
                "organization_name": f"CAP QA Co {self.suffix}",
                "organization_domain": "capqa-test.example",
                "email": email,
                "has_email": True,
                "selected": True,
                "state": "search",
            },
        )
        return line_id

    def _assert_lead_from_ocean(self, rpc: OdooRPCClient, ctx: dict) -> None:
        lead_id = ctx["lead_id"]
        row = rpc.read(
            "crm.lead",
            [lead_id],
            [
                "name",
                "contact_name",
                "partner_name",
                "email_from",
                "function",
                "ocean_person_id",
                "tag_ids",
            ],
        )[0]
        if row.get("ocean_person_id") != ctx.get("ocean_person_id"):
            raise AssertionError(
                f"Lead ocean_person_id {row.get('ocean_person_id')!r} != "
                f"{ctx.get('ocean_person_id')!r}"
            )
        if ctx.get("expected_contact_name") and row.get("contact_name") != ctx["expected_contact_name"]:
            raise AssertionError(
                f"Lead contact_name {row.get('contact_name')!r} != "
                f"{ctx['expected_contact_name']!r}"
            )
        if ctx.get("expected_partner_name") and row.get("partner_name") != ctx["expected_partner_name"]:
            raise AssertionError(
                f"Lead partner_name {row.get('partner_name')!r} != "
                f"{ctx['expected_partner_name']!r}"
            )
        if ctx.get("expected_email") and row.get("email_from") != ctx["expected_email"]:
            raise AssertionError(
                f"Lead email_from {row.get('email_from')!r} != {ctx['expected_email']!r}"
            )
        if ctx.get("expected_contact_name") and not row.get("function"):
            raise AssertionError("Lead function (job title) was not set from Ocean prospect data.")

        tag_ids = row.get("tag_ids") or []
        if tag_ids:
            tags = rpc.read("crm.tag", tag_ids, ["name"])
            if not any(tag.get("name") == OCEAN_TAG_NAME for tag in tags):
                raise AssertionError(f"CRM lead missing {OCEAN_TAG_NAME!r} tag.")
        else:
            raise AssertionError(f"CRM lead has no tags; expected {OCEAN_TAG_NAME!r} tag.")

    def _enrich_lead_via_lookup(self, rpc: OdooRPCClient, ctx: dict) -> None:
        ocean_person_id = ctx.get("ocean_person_id")
        if not ocean_person_id:
            raise AssertionError("No ocean_person_id available for lookup enrichment.")

        enrich_id = rpc.create(
            "ocean.people.enrichment",
            {
                "instance_id": ctx["instance_id"],
                "ocean_person_id": ocean_person_id,
                "lookup_method": "lookup",
            },
        )
        rpc.call("ocean.people.enrichment", "action_enrich", [enrich_id])
        row = rpc.read(
            "ocean.people.enrichment",
            [enrich_id],
            ["state", "enriched_ocean_id", "enriched_name"],
        )[0]
        if row.get("state") != "done":
            raise AssertionError(
                f"People enrichment state {row.get('state')!r}, expected 'done'."
            )
        if row.get("enriched_ocean_id") != ocean_person_id:
            raise AssertionError(
                f"Enriched ocean id {row.get('enriched_ocean_id')!r} != {ocean_person_id!r}"
            )
        if not (row.get("enriched_name") or "").strip():
            raise AssertionError("People enrichment returned no enriched name.")
