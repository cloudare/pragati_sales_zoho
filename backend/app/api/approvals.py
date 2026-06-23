"""
PRD M10 - Multi-level audit & approval workflow.

A document (e.g. credit note) enters an ApprovalRequest tied to a configured
ApprovalChain. Each level approves or rejects:
  - approve at level N → advance to level N+1
  - approve at last level → request becomes 'approved' (downstream effect, e.g. post to Zoho)
  - reject at any level → request becomes 'rejected' (with mandatory remarks)
"""
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import get_current_user, require_roles
from ..models import (
    ApprovalChain, ApprovalChainLevel, ApprovalRequest, ApprovalDecision,
    ApprovalStatus, ApprovalLevelStatus, User, UserRole, AuditLog
)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


# ============================ schemas ============================
class LevelDef(BaseModel):
    level: int = Field(ge=1)
    role: UserRole
    name: Optional[str] = None


class ChainCreate(BaseModel):
    name: str
    entity_type: str
    levels: List[LevelDef] = Field(min_length=1)


class SubmitForApproval(BaseModel):
    chain_id: int
    entity_type: str
    entity_id: str
    entity_label: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class Decision(BaseModel):
    decision: ApprovalLevelStatus    # approved or rejected
    remarks: Optional[str] = None


# ============================ chain admin ============================
@router.post("/chains", dependencies=[Depends(require_roles(UserRole.admin))])
def create_chain(req: ChainCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.query(ApprovalChain).filter(ApprovalChain.name == req.name).first():
        raise HTTPException(status_code=400, detail="Chain with this name already exists")
    levels = sorted(req.levels, key=lambda l: l.level)
    if [l.level for l in levels] != list(range(1, len(levels) + 1)):
        raise HTTPException(status_code=400, detail="Levels must be 1..N consecutive integers")

    chain = ApprovalChain(name=req.name, entity_type=req.entity_type)
    db.add(chain)
    db.flush()
    for l in levels:
        db.add(ApprovalChainLevel(chain_id=chain.id, level=l.level, role=l.role, name=l.name))
    db.commit()
    db.refresh(chain)
    db.add(AuditLog(actor_id=user.id, action="approval_chain.create",
                    entity_type="approval_chain", entity_id=str(chain.id), details={"name": chain.name}))
    db.commit()
    return _chain_out(chain)


@router.get("/chains")
def list_chains(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [_chain_out(c) for c in db.query(ApprovalChain).all()]


def _chain_out(c: ApprovalChain) -> dict:
    return {
        "id": c.id, "name": c.name, "entity_type": c.entity_type, "is_active": c.is_active,
        "levels": [{"level": l.level, "role": l.role.value, "name": l.name} for l in c.levels],
    }


# ============================ submit + act ============================
@router.post("/submit")
def submit(req: SubmitForApproval, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    chain = db.query(ApprovalChain).filter(ApprovalChain.id == req.chain_id,
                                           ApprovalChain.is_active.is_(True)).first()
    if not chain:
        raise HTTPException(status_code=404, detail="Approval chain not found or inactive")

    # Reject duplicate pending request for the same entity
    existing = (db.query(ApprovalRequest)
                .filter(ApprovalRequest.entity_type == req.entity_type,
                        ApprovalRequest.entity_id == req.entity_id,
                        ApprovalRequest.status == ApprovalStatus.pending)
                .first())
    if existing:
        raise HTTPException(status_code=400,
                            detail=f"A pending approval already exists (request {existing.id})")

    ar = ApprovalRequest(
        chain_id=chain.id, entity_type=req.entity_type, entity_id=req.entity_id,
        entity_label=req.entity_label, payload=req.payload, current_level=1,
        submitted_by_id=user.id,
    )
    db.add(ar)
    db.commit()
    db.refresh(ar)
    db.add(AuditLog(actor_id=user.id, action="approval.submit",
                    entity_type=req.entity_type, entity_id=req.entity_id,
                    details={"request_id": ar.id, "chain": chain.name}))
    db.commit()
    return _request_out(db, ar)


@router.get("/inbox")
def inbox(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Pending requests waiting for the current user's role."""
    # Find all pending requests whose current_level role matches user.role (or user is admin)
    pending = (db.query(ApprovalRequest)
               .filter(ApprovalRequest.status == ApprovalStatus.pending)
               .all())
    out = []
    for r in pending:
        chain = r.chain
        cur_level = next((l for l in chain.levels if l.level == r.current_level), None)
        if not cur_level:
            continue
        if user.role == UserRole.admin or user.role == cur_level.role:
            out.append(_request_out(db, r))
    return out


@router.get("/requests/{request_id}")
def get_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(ApprovalRequest).filter(ApprovalRequest.id == request_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    return _request_out(db, r)


@router.post("/requests/{request_id}/decide")
def decide(request_id: int, req: Decision, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(ApprovalRequest).filter(ApprovalRequest.id == request_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    if r.status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail=f"Request is already {r.status.value}")

    chain = r.chain
    cur_level = next((l for l in chain.levels if l.level == r.current_level), None)
    if not cur_level:
        raise HTTPException(status_code=500, detail="Chain configuration error - missing level")

    # Authorisation: must be admin or have the role expected at this level
    if user.role != UserRole.admin and user.role != cur_level.role:
        raise HTTPException(status_code=403,
                            detail=f"This level requires role '{cur_level.role.value}'")

    # Reject requires remarks
    if req.decision == ApprovalLevelStatus.rejected and not (req.remarks or "").strip():
        raise HTTPException(status_code=400, detail="Remarks are mandatory when rejecting")

    # Record decision
    d = ApprovalDecision(
        request_id=r.id, level=r.current_level, decider_user_id=user.id,
        decision=req.decision, remarks=req.remarks,
    )
    db.add(d)

    # Apply state machine
    if req.decision == ApprovalLevelStatus.rejected:
        r.status = ApprovalStatus.rejected
        r.completed_at = datetime.now(timezone.utc)
    elif req.decision == ApprovalLevelStatus.approved:
        max_level = max(l.level for l in chain.levels)
        if r.current_level >= max_level:
            r.status = ApprovalStatus.approved
            r.completed_at = datetime.now(timezone.utc)
        else:
            r.current_level += 1

    db.commit()
    db.refresh(r)
    db.add(AuditLog(actor_id=user.id, action=f"approval.{req.decision.value}",
                    entity_type=r.entity_type, entity_id=r.entity_id,
                    details={"request_id": r.id, "level": d.level,
                             "remarks": req.remarks, "new_status": r.status.value}))
    db.commit()
    return _request_out(db, r)


def _request_out(db: Session, r: ApprovalRequest) -> dict:
    chain = r.chain
    cur_level = next((l for l in chain.levels if l.level == r.current_level), None)
    return {
        "id": r.id,
        "chain": {"id": chain.id, "name": chain.name, "entity_type": chain.entity_type},
        "entity_type": r.entity_type, "entity_id": r.entity_id,
        "entity_label": r.entity_label,
        "status": r.status.value,
        "current_level": r.current_level,
        "current_level_role": cur_level.role.value if cur_level else None,
        "current_level_name": cur_level.name if cur_level else None,
        "max_level": max(l.level for l in chain.levels),
        "submitted_by": r.submitted_by.username if r.submitted_by else None,
        "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "payload": r.payload,
        "decisions": [{
            "level": d.level, "decider": d.decider.username if d.decider else None,
            "decision": d.decision.value, "remarks": d.remarks,
            "decided_at": d.decided_at.isoformat() if d.decided_at else None,
        } for d in r.decisions],
    }


# ============================ helper for callers ============================
def is_approved(db: Session, entity_type: str, entity_id: str) -> bool:
    """Helper for other modules - has this entity been approved?"""
    r = (db.query(ApprovalRequest)
         .filter(ApprovalRequest.entity_type == entity_type,
                 ApprovalRequest.entity_id == entity_id,
                 ApprovalRequest.status == ApprovalStatus.approved)
         .first())
    return r is not None
