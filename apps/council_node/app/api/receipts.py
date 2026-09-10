"""Receipt retrieval and verification."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..deps import services
from ..receipts.schema import ReceiptError
from ..receipts.verifier import verify_receipt

router = APIRouter(prefix="/api/receipts", tags=["receipts"])


@router.get("")
def list_receipts(limit: int = 50) -> dict:
    ids = services().receipts.list_ids()
    return {"count": len(ids), "receipt_ids": ids[-limit:]}


@router.get("/{receipt_id}")
def get_receipt(receipt_id: str) -> dict:
    try:
        receipt = services().receipts.read(receipt_id)
    except ReceiptError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result = verify_receipt(receipt)
    return {
        "receipt": receipt.to_dict(),
        "verification": {
            "valid": result.valid,
            "hash_valid": result.hash_valid,
            "sanitized": result.sanitized,
            "claim_supported": result.claim_supported,
            "reasons": list(result.reasons),
        },
    }
