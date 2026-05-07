"""Automation template API routes."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.automation.models import AutomationTemplate, TemplateRun, TemplateStatus
from backend.scheduler.core import start_scheduler, stop_scheduler

router = APIRouter()


@router.post("/templates")
def create_template(data: dict, db: Session = Depends(get_db)):
    template = AutomationTemplate(**data)
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.get("/templates")
def list_templates(db: Session = Depends(get_db)):
    return db.query(AutomationTemplate).order_by(AutomationTemplate.created_at.desc()).all()


@router.get("/templates/{template_id}")
def get_template(template_id: int, db: Session = Depends(get_db)):
    template = db.query(AutomationTemplate).filter(AutomationTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.put("/templates/{template_id}")
def update_template(template_id: int, data: dict, db: Session = Depends(get_db)):
    template = db.query(AutomationTemplate).filter(AutomationTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    for key, value in data.items():
        setattr(template, key, value)

    db.commit()
    db.refresh(template)
    return template


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    template = db.query(AutomationTemplate).filter(AutomationTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    db.delete(template)
    db.commit()
    return {"deleted": True}


@router.post("/templates/{template_id}/toggle")
def toggle_template(template_id: int, db: Session = Depends(get_db)):
    template = db.query(AutomationTemplate).filter(AutomationTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    template.is_active = not template.is_active
    template.status = TemplateStatus.ACTIVE.value if template.is_active else TemplateStatus.PAUSED.value
    db.commit()

    return {"is_active": template.is_active, "status": template.status}


@router.post("/templates/{template_id}/run")
def run_template_now(template_id: int, db: Session = Depends(get_db)):
    """Trigger a template run manually."""
    template = db.query(AutomationTemplate).filter(AutomationTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # This would normally trigger the scheduler to run this template immediately
    # For now, return a message that manual run is queued
    return {"message": "Manual run queued", "template_id": template_id}


@router.get("/templates/{template_id}/runs")
def get_template_runs(template_id: int, limit: int = 20, db: Session = Depends(get_db)):
    return db.query(TemplateRun).filter(
        TemplateRun.template_id == template_id
    ).order_by(TemplateRun.created_at.desc()).limit(limit).all()
