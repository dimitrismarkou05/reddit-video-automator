"""FastAPI orchestration routes no business logic."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Subreddit, Story, Setting
from backend.schemas import (
    SubredditCreate,
    SubredditResponse,
    StoryResponse,
    StoryDetailResponse,
    StoryChainResponse,
    FetchResult,
    SettingsUpdate,
    SettingsResponse,
)
from backend.reddit.fetcher import StoryFetcher
from backend.reddit.linker import UpdateLinker
from backend.settings_manager import SettingsManager

router = APIRouter()


# Subreddits
@router.post("/subreddits", response_model=SubredditResponse)
def add_subreddit(data: SubredditCreate, db: Session = Depends(get_db)):
    fetcher = StoryFetcher(db)
    try:
        return fetcher.add_subreddit(data.name, data.fetch_settings or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/subreddits", response_model=List[SubredditResponse])
def list_subreddits(active_only: bool = False, db: Session = Depends(get_db)):
    q = db.query(Subreddit)
    if active_only:
        q = q.filter(Subreddit.is_active.is_(True))
    return q.all()


@router.delete("/subreddits/{subreddit_id}")
def delete_subreddit(subreddit_id: int, db: Session = Depends(get_db)):
    sub = db.query(Subreddit).filter(Subreddit.id == subreddit_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subreddit not found")
    db.delete(sub)
    db.commit()
    return {"deleted": True}


@router.post("/subreddits/{subreddit_id}/fetch", response_model=FetchResult)
def fetch_subreddit(subreddit_id: int, db: Session = Depends(get_db)):
    fetcher = StoryFetcher(db)
    sub = db.query(Subreddit).filter(Subreddit.id == subreddit_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subreddit not found")

    try:
        stories = fetcher.fetch_stories(subreddit_id)
        return FetchResult(subreddit=sub.name, fetched_count=len(stories), error=None)
    except Exception as exc:
        return FetchResult(subreddit=sub.name, fetched_count=0, error=str(exc))


@router.post("/fetch-all", response_model=List[FetchResult])
def fetch_all(db: Session = Depends(get_db)):
    fetcher = StoryFetcher(db)
    results = fetcher.fetch_all_active()
    return [
        FetchResult(subreddit=name, fetched_count=len(stories), error=None)
        for name, stories in results.items()
    ]


# Stories
@router.get("/stories", response_model=List[StoryResponse])
def list_stories(
    subreddit: Optional[str] = None,
    status: Optional[str] = None,
    is_update: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Story)
    if subreddit:
        q = q.filter(Story.subreddit == subreddit)
    if status:
        q = q.filter(Story.status == status)
    if is_update is not None:
        q = q.filter(Story.is_update == is_update)
    return q.order_by(Story.fetched_at.desc()).all()


@router.get("/stories/{story_id}", response_model=StoryDetailResponse)
def get_story(story_id: int, db: Session = Depends(get_db)):
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.get("/stories/{story_id}/chain", response_model=StoryChainResponse)
def get_story_chain(story_id: int, db: Session = Depends(get_db)):
    linker = UpdateLinker(db)
    chain = linker.get_story_chain(story_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Story not found")
    return StoryChainResponse(original=chain[0], updates=chain[1:])


@router.post("/stories/link-updates")
def run_link_updates(subreddit: Optional[str] = None, db: Session = Depends(get_db)):
    linker = UpdateLinker(db)
    if subreddit:
        count = linker.link_updates_for_subreddit(subreddit)
    else:
        count = 0
        for (sub_name,) in db.query(Story.subreddit).distinct().all():
            count += linker.link_updates_for_subreddit(sub_name)
    return {"linked_count": count}


# Settings
@router.get("/settings/{key}", response_model=SettingsResponse)
def get_setting(key: str, db: Session = Depends(get_db)):
    setting = db.query(Setting).filter(Setting.key == key).first()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")

    value = setting.value
    if setting.is_encrypted:
        value = "••••••••"

    return SettingsResponse(
        key=setting.key,
        value=value,
        is_encrypted=setting.is_encrypted,
        updated_at=setting.updated_at,
    )


@router.post("/settings", response_model=SettingsResponse)
def set_setting(data: SettingsUpdate, db: Session = Depends(get_db)):
    mgr = SettingsManager(db)
    setting = mgr.set(data.key, data.value, encrypt_value=data.encrypt)

    value = setting.value
    if setting.is_encrypted:
        value = "••••••••"

    return SettingsResponse(
        key=setting.key,
        value=value,
        is_encrypted=setting.is_encrypted,
        updated_at=setting.updated_at,
    )