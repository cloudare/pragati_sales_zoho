"""Scheme CRUD + evaluation preview."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from ..core.database import get_db
from ..core.deps import get_current_user, require_roles
from ..models import Scheme, SchemeType, User, UserRole, AuditLog
from ..services.scheme_engine import evaluate_schemes

router = APIRouter(prefix="/api/schemes", tags=["schemes"])


class SchemeIn(BaseModel):
    code: str
    name: str
    scheme_type: SchemeType
    valid_from: datetime
    valid_to: datetime
    priority: int = 100
    stackable: bool = False
    min_margin_pct: float = 0
    applicability: Dict[str, Any] = {}
    rule: Dict[str, Any] = {}
    is_active: bool = True


@router.post("")
def create_scheme(
    payload: SchemeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.accounts, UserRole.sales)),
):
    if db.query(Scheme).filter(Scheme.code == payload.code).first():
        raise HTTPException(400, "Scheme code already exists")
    s = Scheme(**payload.model_dump(), created_by_id=user.id)
    db.add(s)
    db.flush()
    db.add(AuditLog(actor_id=user.id, action="scheme.create", entity_type="scheme", entity_id=str(s.id)))
    db.commit()
    db.refresh(s)
    return _serialize(s)


@router.get("")
def list_schemes(active_only: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Scheme).order_by(Scheme.priority.asc(), Scheme.id.desc())
    if active_only:
        q = q.filter(Scheme.is_active == True)
    return [_serialize(s) for s in q.all()]


@router.get("/{scheme_id}")
def get_scheme(scheme_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = db.query(Scheme).get(scheme_id)
    if not s:
        raise HTTPException(404)
    return _serialize(s)


@router.put("/{scheme_id}")
def update_scheme(
    scheme_id: int,
    payload: SchemeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.accounts)),
):
    s = db.query(Scheme).get(scheme_id)
    if not s:
        raise HTTPException(404)
    for k, v in payload.model_dump().items():
        setattr(s, k, v)
    db.add(AuditLog(actor_id=user.id, action="scheme.update", entity_type="scheme", entity_id=str(s.id)))
    db.commit()
    db.refresh(s)
    return _serialize(s)


@router.delete("/{scheme_id}")
def delete_scheme(
    scheme_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin)),
):
    s = db.query(Scheme).get(scheme_id)
    if not s:
        raise HTTPException(404)
    s.is_active = False
    db.add(AuditLog(actor_id=user.id, action="scheme.deactivate", entity_type="scheme", entity_id=str(s.id)))
    db.commit()
    return {"ok": True}


# ---------- EVALUATE PREVIEW ----------
class EvaluateRequest(BaseModel):
    party_id: str = ""
    party_group: Optional[str] = None
    lines: List[Dict[str, Any]]
    # each line: {item_zoho_id, item_name, qty, rate, cost?, brand?}


@router.post("/evaluate")
def evaluate(req: EvaluateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Preview which schemes apply to a draft cart. Used by sales UI before invoice creation."""
    return evaluate_schemes(db, req.party_id, req.party_group, req.lines)


def _serialize(s: Scheme) -> dict:
    return {
        "id": s.id,
        "code": s.code,
        "name": s.name,
        "scheme_type": s.scheme_type.value,
        "valid_from": s.valid_from,
        "valid_to": s.valid_to,
        "priority": s.priority,
        "stackable": s.stackable,
        "min_margin_pct": s.min_margin_pct,
        "applicability": s.applicability,
        "rule": s.rule,
        "is_active": s.is_active,
    }
