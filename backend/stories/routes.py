"""Story management and update linking routes."""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session, joinedload

from core.database import get_db
from stories.models import Story
from stories.schemas import StoryResponse, StoryDetailResponse, StoryChainResponse, StoryListResponse
from services.notification_service import NotificationService
from stories.linker.core import UpdateLinker

router = APIRouter()


@router.get("", response_model=StoryListResponse)
def list_stories(
    page: int = Query(1, ge=1, description="1-based page index"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    subreddit: Optional[str] = None,
    status: Optional[str] = None,
    is_update: Optional[bool] = None,
    sort_by: Optional[str] = Query(None, pattern="^(date_desc|date_asc|score_desc|score_asc|title_asc)$"),
    db: Session = Depends(get_db),
):
    # Build base query - only parent stories by default for pagination
    if is_update is None:
        is_update = False

    base_query = db.query(Story).filter(Story.is_update == is_update)

    if subreddit:
        base_query = base_query.filter(Story.subreddit == subreddit)
    if status:
        base_query = base_query.filter(Story.status == status)

    # Apply sorting
    if sort_by == "date_asc":
        base_query = base_query.order_by(Story.created_utc.asc())
    elif sort_by == "score_desc":
        base_query = base_query.order_by(Story.score.desc())
    elif sort_by == "score_asc":
        base_query = base_query.order_by(Story.score.asc())
    elif sort_by == "title_asc":
        base_query = base_query.order_by(Story.title.asc())
    else:
        base_query = base_query.order_by(Story.created_utc.desc())

    # Get total count
    total = base_query.with_entities(func.count()).scalar()

    # Apply pagination
    stories = (
        base_query
        .options(joinedload(Story.updates))
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    pages = (total + limit - 1) // limit

    return StoryListResponse(
        items=stories,
        total=total,
        page=page,
        pages=max(1, pages),
        limit=limit,
    )


@router.get("/{story_id}", response_model=StoryDetailResponse)
def get_story(story_id: int, db: Session = Depends(get_db)):
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.delete("/{story_id}")
def delete_story(story_id: int, db: Session = Depends(get_db)):
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    update_count = len(story.updates) if story.updates else 0
    title = story.title[:50]

    db.delete(story)
    db.commit()

    update_word = "update" if update_count == 1 else "updates"
    NotificationService(db).create(
        "story", "warning",
        f'Deleted story "{title}..." and {update_count} {update_word}',
        {"story_id": story_id, "updates_deleted": update_count},
    )
    return {
        "deleted": True,
        "story_id": story_id,
        "title": title,
        "updates_deleted": update_count,
    }


@router.delete("")
def delete_all_stories(db: Session = Depends(get_db)):
    count = db.query(Story).count()

    if count == 0:
        NotificationService(db).create(
            "story", "info",
            "No stories available to delete",
            {"reason": "no_stories"},
        )
        return {"deleted": False, "count": 0, "message": "No stories available to delete"}

    db.query(Story).delete()
    db.commit()

    story_word = "story" if count == 1 else "stories"
    NotificationService(db).create(
        "story", "warning",
        f"Deleted all {count} {story_word}",
        {"deleted_count": count},
    )
    return {"deleted": True, "count": count}


@router.get("/{story_id}/chain", response_model=StoryChainResponse)
def get_story_chain(story_id: int, db: Session = Depends(get_db)):
    linker = UpdateLinker(db)
    chain = linker.get_story_chain(story_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Story not found")
    return StoryChainResponse(original=chain[0], updates=chain[1:])


@router.post("/link-updates")
def run_link_updates(subreddit: Optional[str] = None, db: Session = Depends(get_db)):
    linker = UpdateLinker(db)
    if subreddit:
        subreddits_processed = [subreddit]
        count = linker.link_updates_for_subreddit(subreddit)
    else:
        subreddits_processed = [name for (name,) in db.query(Story.subreddit).distinct().all()]
        count = 0
        for sub_name in subreddits_processed:
            count += linker.link_updates_for_subreddit(sub_name)

    if not subreddits_processed:
        NotificationService(db).create(
            "story", "info",
            "No active subreddits to link updates",
            {"linked_count": 0, "reason": "no_subreddits"},
        )
        return {
            "linked_count": 0,
            "reason": "no_subreddits",
            "message": "No active subreddits to link updates",
        }
    elif count == 0:
        NotificationService(db).create(
            "story", "info",
            "No update stories found to link",
            {"linked_count": 0, "reason": "no_updates"},
        )
        return {
            "linked_count": 0,
            "reason": "no_updates",
            "message": "No update stories found to link",
        }

    story_word = "story" if count == 1 else "stories"
    NotificationService(db).create(
        "story", "success",
        f"Linked {count} update {story_word}",
        {"linked_count": count},
    )
    return {"linked_count": count, "message": f"Linked {count} update {story_word}"}
