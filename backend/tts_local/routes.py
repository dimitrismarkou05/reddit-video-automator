"""Local TTS model API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from services.tts_service import TTSService
from tts_local.schemas import TtsStatusResponse

router = APIRouter()


@router.get("/status", response_model=TtsStatusResponse)
def get_tts_status(db: Session = Depends(get_db)):
    service = TTSService(db)
    return service.get_status()


@router.get("/voices")
def list_voices(db: Session = Depends(get_db)):
    service = TTSService(db)
    return service.list_voices()
