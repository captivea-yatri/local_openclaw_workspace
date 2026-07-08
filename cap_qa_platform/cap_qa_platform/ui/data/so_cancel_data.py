"""Load test data for so_cancel_old_customer UI flow (RPC)."""
from __future__ import annotations

from dataclasses import dataclass, field

from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.scenarios.so_base import SoScenarioBase


@dataclass
class SoCancelUiData:
    partner_id: int
    partner_name: str
    offer_name: str
    business_unit_name: str
    business_localisation_name: str
    product_names: list[str] = field(default_factory=list)


def prepare_so_cancel_data(
    tester: OdooRPCClient,
    admin: OdooRPCClient,
    fallback_partner_id: int | None = None,
) -> tuple[SoCancelUiData, SoScenarioBase]:
    base = SoScenarioBase(fallback_partner_id=fallback_partner_id)
    base.bind_admin(admin)
    base._authenticate(tester)

    from cap_qa_platform.scenarios.base import ScenarioRunResult

    result = ScenarioRunResult(scenario="so_cancel_old_customer", role_name="ui", success=False)
    partner_id = base._resolve_partner(tester, result)
    partner_name = tester.read("res.partner", [partner_id], ["name"])[0]["name"]

    offer = base._find_assistance_offer(tester)
    products = base._find_two_service_products(tester, offer["id"])

    bu_id = m2o_id(offer.get("business_unit_ids"))
    if not bu_id:
        bu_id = (offer.get("business_unit_ids") or [None])[0]
    loc_id = m2o_id(offer.get("business_localisation_ids"))
    if not loc_id:
        loc_id = (offer.get("business_localisation_ids") or [None])[0]
    if not bu_id or not loc_id:
        raise RuntimeError("Assistance offer missing business unit or localisation.")

    bu_name = tester.read("business.unit", [bu_id], ["name"])[0]["name"]
    loc_name = tester.read("business.localisation", [loc_id], ["name"])[0]["name"]

    return (
        SoCancelUiData(
            partner_id=partner_id,
            partner_name=partner_name,
            offer_name=offer["name"],
            business_unit_name=bu_name,
            business_localisation_name=loc_name,
            product_names=[p["name"] for p in products],
        ),
        base,
    )
