"""Fail-closed adapters for historical revenue snapshots.

Adapters accept local, already-exported records only. They do not call external APIs,
read secrets, contact customers, or mutate source systems.
"""
from __future__ import annotations
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from .canonical import sha256_json
HASH_PATTERN=re.compile(r"^[0-9a-f]{64}$")
VALID_SOURCE_SYSTEMS={"REPOSITORY_FIXTURE","WIX_EXPORT","PAYMENT_EXPORT","ANALYTICS_EXPORT","MANUAL_VERIFIED_EXPORT"}
VALID_BUSINESS_STATUSES={"REPOSITORY_TEST_FIXTURE","ACTUAL_BUSINESS_HISTORY"}
COUNT_FIELDS=("visitors","leads","qualified_leads","proposals","purchases")
MONEY_FIELDS=("revenue","variable_cost","fixed_cost")
MONEY=Decimal("0.01")
def _decimal(value:Any,field:str)->Decimal:
    try: result=Decimal(str(value))
    except Exception as exc: raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite(): raise ValueError(f"{field} must be finite")
    return result
def _parse_date(value:Any,field:str)->date:
    if not isinstance(value,str): raise ValueError(f"{field} must be an ISO date")
    try: return date.fromisoformat(value)
    except ValueError as exc: raise ValueError(f"{field} must be an ISO date") from exc
def _parse_timestamp(value:Any)->None:
    if not isinstance(value,str) or not value: raise ValueError("as_of must be an ISO timestamp")
    try: datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as exc: raise ValueError("as_of must be an ISO timestamp") from exc
def _period_to_scenario(period:dict[str,Any],label:str)->tuple[dict[str,Any]|None,list[str]]:
    errors=[]
    if not isinstance(period,dict): return None,[f"{label}_period_must_be_object"]
    try:
        start=_parse_date(period.get("period_start"),f"{label}.period_start"); end=_parse_date(period.get("period_end"),f"{label}.period_end")
        if end<start: errors.append(f"{label}_period_end_before_start")
    except ValueError as exc: errors.append(str(exc))
    counts={}
    for field in COUNT_FIELDS:
        value=period.get(field)
        if isinstance(value,bool) or not isinstance(value,int) or value<0: errors.append(f"{label}.{field}_must_be_nonnegative_integer")
        else: counts[field]=value
    if len(counts)==len(COUNT_FIELDS):
        sequence=[counts[f] for f in COUNT_FIELDS]
        if any(a<b for a,b in zip(sequence,sequence[1:])): errors.append(f"{label}_funnel_counts_not_monotonic")
    money={}
    for field in MONEY_FIELDS:
        try:
            value=_decimal(period.get(field),f"{label}.{field}")
            if value<0: errors.append(f"{label}.{field}_must_be_nonnegative")
            money[field]=value
        except ValueError as exc: errors.append(str(exc))
    if errors: return None,errors
    visitors=counts["visitors"]; leads=counts["leads"]; qualified=counts["qualified_leads"]; proposals=counts["proposals"]; purchases=counts["purchases"]
    def rate(n:int,d:int)->str: return "0" if d==0 else str((Decimal(n)/Decimal(d)).quantize(Decimal("0.00000001"),rounding=ROUND_HALF_UP))
    scenario={"visitors":visitors,"visitor_to_lead_rate":rate(leads,visitors),"lead_to_qualified_rate":rate(qualified,leads),"qualified_to_proposal_rate":rate(proposals,qualified),"proposal_to_purchase_rate":rate(purchases,proposals),"average_order_value":"0" if purchases==0 else str((money["revenue"]/Decimal(purchases)).quantize(MONEY,rounding=ROUND_HALF_UP)),"variable_cost_per_purchase":"0" if purchases==0 else str((money["variable_cost"]/Decimal(purchases)).quantize(MONEY,rounding=ROUND_HALF_UP)),"fixed_cost":str(money["fixed_cost"].quantize(MONEY,rounding=ROUND_HALF_UP))}
    return scenario,[]
def adapt_historical_snapshot(snapshot:dict[str,Any])->dict[str,Any]:
    if not isinstance(snapshot,dict): raise TypeError("snapshot must be an object")
    errors=[]; required={"snapshot_id","source_system","business_data_status","as_of","evidence","periods","payload_hash","contains_personal_data","contains_secret_material"}; errors.extend(f"missing_field:{f}" for f in sorted(required-set(snapshot)))
    source_system=snapshot.get("source_system"); business_status=snapshot.get("business_data_status")
    if source_system not in VALID_SOURCE_SYSTEMS: errors.append("invalid_source_system")
    if business_status not in VALID_BUSINESS_STATUSES: errors.append("invalid_business_data_status")
    if business_status=="ACTUAL_BUSINESS_HISTORY" and source_system=="REPOSITORY_FIXTURE": errors.append("fixture_source_cannot_claim_actual_business_history")
    try: _parse_timestamp(snapshot.get("as_of"))
    except ValueError as exc: errors.append(str(exc))
    evidence=snapshot.get("evidence",[])
    if not isinstance(evidence,list) or not evidence or not all(isinstance(i,str) and i for i in evidence): errors.append("evidence_must_be_nonempty_string_list")
    if snapshot.get("contains_personal_data") is not False: errors.append("personal_data_not_permitted_in_stage4_snapshot")
    if snapshot.get("contains_secret_material") is not False: errors.append("secret_material_not_permitted_in_stage4_snapshot")
    periods=snapshot.get("periods",{})
    if not isinstance(periods,dict): errors.append("periods_must_be_object"); periods={}
    payload_hash=snapshot.get("payload_hash")
    if not isinstance(payload_hash,str) or not HASH_PATTERN.fullmatch(payload_hash): errors.append("invalid_payload_hash")
    elif payload_hash!=sha256_json(periods): errors.append("payload_hash_mismatch")
    baseline,base_errors=_period_to_scenario(periods.get("baseline"),"baseline"); candidate,cand_errors=_period_to_scenario(periods.get("candidate"),"candidate"); errors.extend(base_errors+cand_errors)
    if errors: status="HOLD"; source_kind=None
    elif business_status=="ACTUAL_BUSINESS_HISTORY": status="VERIFIED"; source_kind="HISTORICAL_VERIFIED"
    else: status="TEST_ONLY"; source_kind="SYNTHETIC_TEST"
    result={"mode":"SHADOW_ONLY","snapshot_id":snapshot.get("snapshot_id"),"snapshot_hash":sha256_json(snapshot),"status":status,"source_kind":source_kind,"business_data_status":business_status,"source_system":source_system,"as_of":snapshot.get("as_of"),"evidence":evidence if isinstance(evidence,list) else [],"errors":sorted(set(errors)),"baseline":baseline,"candidate":candidate,"external_actions":[],"source_system_mutated":False,"money_moved":False,"customers_contacted":False,"content_published":False,"production_changes":False}
    result["adapter_result_hash"]=sha256_json(result); return result
