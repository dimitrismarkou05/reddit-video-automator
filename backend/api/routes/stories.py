"""Story management and update linking routes."""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import Story
from schemas import StoryResponse, StoryDetailResponse, StoryChainResponse
from services.notification_service import NotificationService
from reddit.linker import UpdateLinker

router = APIRouter(tags=["Stories"])


@router.get("/stories", response_model=List[StoryResponse])
def list_stories(
    subreddit: Optional[str] = None,
    status: Optional[str] = None,
    is_update: Optional[bool] = None,
    sort_by: Optional[str] = None,
    db: Session = Depends(get_db),
):
    stmt = select(Story).options(joinedload(Story.updates))

    if subreddit:
        stmt = stmt.where(Story.subreddit == subreddit)
    if status:
        stmt = stmt.where(Story.status == status)
    if is_update is not None:
        stmt = stmt.where(Story.is_update == is_update)

    if sort_by == "date_asc":
        stmt = stmt.order_by(Story.created_utc.asc())
    elif sort_by == "score_desc":
        stmt = stmt.order_by(Story.score.desc())
    elif sort_by == "score_asc":
        stmt = stmt.order_by(Story.score.asc())
    elif sort_by == "title_asc":
        stmt = stmt.order_by(Story.title.asc())
    else:
        stmt = stmt.order_by(Story.created_utc.desc())

    result = db.execute(stmt)
    return result.unique().scalars().all()


@router.get("/stories/{story_id}", response_model=StoryDetailResponse)
def get_story(story_id: int, db: Session = Depends(get_db)):
    story = db.query(Story).filter(Story.id == story_id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@router.delete("/stories/{story_id}")
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


@router.delete("/stories")
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
