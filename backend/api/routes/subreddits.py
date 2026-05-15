"""Subreddit management and story fetching routes."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Subreddit, Story
from schemas import (
    SubredditCreate,
    SubredditResponse,
    FetchResult,
    FetchRequest,
)
from services.notification_service import NotificationService
from reddit.fetcher import StoryFetcher, SubredditAccessError
from reddit.client import RateLimitError
from automation.routes import router as automation_router

router = APIRouter(tags=["Subreddits"])


def _handle_fetch_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RateLimitError):
        return HTTPException(status_code=429, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=f"Internal error: {exc}")


@router.post("/subreddits", response_model=SubredditResponse)
def add_subreddit(
    data: SubredditCreate, force: bool = False, db: Session = Depends(get_db)
):
    fetcher = StoryFetcher(db)
    try:
        return fetcher.add_subreddit(data.name, data.fetch_settings or {}, force=force)
    except SubredditAccessError as exc:
        status_code = 403 if exc.is_private else 400
        raise HTTPException(
            status_code=status_code,
            detail={
                "message": str(exc),
                "is_private": exc.is_private,
                "subreddit": data.name,
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": str(exc),
                "is_private": False,
                "subreddit": data.name,
            },
        )


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

    story_count = db.query(Story).filter(Story.subreddit == sub.name).count()
    db.query(Story).filter(Story.subreddit == sub.name).delete()
    db.delete(sub)
    db.commit()

    if story_count == 0:
        message = f"Deleted r/{sub.name}"
    else:
        story_word = "story" if story_count == 1 else "stories"
        message = f"Deleted r/{sub.name} and {story_count} {story_word}"

    NotificationService(db).create(
        "subreddit", "warning", message,
        {"subreddit": sub.name, "deleted_stories": story_count},
    )
    return {"deleted": True, "subreddit": sub.name, "stories_deleted": story_count}


@router.delete("/subreddits")
def delete_all_subreddits(db: Session = Depends(get_db)):
    subreddits = db.query(Subreddit).all()
    total_stories = 0
    for sub in subreddits:
        total_stories += db.query(Story).filter(Story.subreddit == sub.name).count()

    count = db.query(Subreddit).delete()
    db.query(Story).delete()
    db.commit()

    story_word = "story" if total_stories == 1 else "stories"
    single_sub_name = subreddits[0].name if count == 1 and subreddits else None

    if count == 1 and single_sub_name:
        if total_stories == 0:
            message = f"Deleted r/{single_sub_name}"
        else:
            message = f"Deleted r/{single_sub_name} and {total_stories} {story_word}"
    else:
        sub_word = "subreddit" if count == 1 else "subreddits"
        if total_stories == 0:
            message = f"Deleted {count} {sub_word}"
        else:
            message = f"Deleted {count} {sub_word} and {total_stories} {story_word}"

    NotificationService(db).create(
        "subreddit", "warning", message,
        {"deleted_subreddits": count, "deleted_stories": total_stories},
    )
    return {
        "deleted": True,
        "count": count,
        "stories_deleted": total_stories,
        "subreddit_name": single_sub_name,
    }


@router.post("/subreddits/{subreddit_id}/fetch", response_model=FetchResult)
def fetch_subreddit(subreddit_id: int, db: Session = Depends(get_db)):
    fetcher = StoryFetcher(db)
    sub = db.query(Subreddit).filter(Subreddit.id == subreddit_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subreddit not found")

    try:
        stories, metadata = fetcher.fetch_stories(subreddit_id)
        _notify_fetch_result(db, sub.name, stories, metadata)
        return FetchResult(subreddit=sub.name, fetched_count=len(stories), error=None)
    except RateLimitError as exc:
        raise _handle_fetch_error(exc)
    except Exception as exc:
        NotificationService(db).create(
            "story", "error",
            f"Failed to fetch r/{sub.name}: {exc}",
            {"subreddit": sub.name},
        )
        return FetchResult(subreddit=sub.name, fetched_count=0, error=str(exc))


@router.get("/fetch-preview")
def fetch_preview(db: Session = Depends(get_db)):
    fetcher = StoryFetcher(db)
    active_count = db.query(Subreddit).filter(Subreddit.is_active.is_(True)).count()
    return fetcher.get_rate_limit_preview(active_count)


@router.post("/fetch", response_model=List[FetchResult])
def fetch_stories_endpoint(request: FetchRequest, db: Session = Depends(get_db)):
    fetcher = StoryFetcher(db)

    if request.sort not in ("top", "new"):
        raise HTTPException(status_code=400, detail="sort must be top or new")
    if request.sort == "top" and request.time_filter not in ("day", "week", "month", "year", "all"):
        raise HTTPException(status_code=400, detail="time_filter must be day, week, month, year, or all")
    if request.limit not in (5, 10, 15, 20, 25):
        raise HTTPException(status_code=400, detail="limit must be 5, 10, 15, 20, or 25")

    if request.subreddit_id is not None:
        return _fetch_single(db, fetcher, request)
    return _fetch_all_active(db, fetcher, request)


@router.post("/fetch-all", response_model=List[FetchResult])
def fetch_all(db: Session = Depends(get_db)):
    fetcher = StoryFetcher(db)
    results, errors, metadata = fetcher.fetch_all_active()

    if not results and not errors:
        NotificationService(db).create(
            "story", "info",
            "No active subreddits to fetch stories",
            {"reason": "no_active_subreddits"},
        )
        return []

    return _build_fetch_results(db, results, errors, metadata)


def _fetch_single(db: Session, fetcher: StoryFetcher, request: FetchRequest) -> List[FetchResult]:
    sub = db.query(Subreddit).filter(Subreddit.id == request.subreddit_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subreddit not found")

    try:
        stories, metadata = fetcher.fetch_stories(
            subreddit_id=request.subreddit_id,
            sort=request.sort,
            time_filter=request.time_filter if request.sort == "top" else "week",
            limit=request.limit,
        )
        _notify_fetch_result(db, sub.name, stories, metadata)
        return [FetchResult(subreddit=sub.name, fetched_count=len(stories), error=None)]
    except RateLimitError as exc:
        raise _handle_fetch_error(exc)
    except Exception as exc:
        NotificationService(db).create(
            "story", "error",
            f"Failed to fetch r/{sub.name}: {exc}",
            {"subreddit": sub.name},
        )
        return [FetchResult(subreddit=sub.name, fetched_count=0, error=str(exc))]


def _fetch_all_active(db: Session, fetcher: StoryFetcher, request: FetchRequest) -> List[FetchResult]:
    results, errors, metadata = fetcher.fetch_all_active(
        sort=request.sort,
        time_filter=request.time_filter if request.sort == "top" else "week",
        limit=request.limit,
    )

    if not results and not errors:
        NotificationService(db).create(
            "story", "info",
            "No active subreddits to fetch stories",
            {"reason": "no_active_subreddits"},
        )
        return []

    return _build_fetch_results(db, results, errors, metadata)


def _build_fetch_results(
    db: Session, results: dict, errors: dict, metadata: dict
) -> List[FetchResult]:
    fetch_results = []
    for name, stories in results.items():
        error = errors.get(name)
        if error:
            NotificationService(db).create(
                "story", "error",
                f"Failed to fetch r/{name}: {error}",
                {"subreddit": name},
            )
        elif len(stories) == 0:
            sub_meta = metadata.get(f"{name}_meta", {})
            if sub_meta.get("has_more"):
                NotificationService(db).create(
                    "story", "info",
                    f"No new stories found in r/{name} (all already fetched, more pages available)",
                    {"subreddit": name, "count": 0, "has_more": True},
                )
            else:
                NotificationService(db).create(
                    "story", "info",
                    f"No new stories found in r/{name} (all already fetched)",
                    {"subreddit": name, "count": 0},
                )
        else:
            story_word = "story" if len(stories) == 1 else "stories"
            NotificationService(db).create(
                "story", "success",
                f"Fetched {len(stories)} new {story_word} from r/{name}",
                {"subreddit": name, "count": len(stories)},
            )
        fetch_results.append(
            FetchResult(subreddit=name, fetched_count=len(stories), error=error)
        )
    return fetch_results


def _notify_fetch_result(db: Session, sub_name: str, stories: list, metadata: dict) -> None:
    if len(stories) == 0:
        if metadata.get("has_more"):
            NotificationService(db).create(
                "story", "info",
                f"No new stories found in r/{sub_name} (all already fetched, more pages available)",
                {"subreddit": sub_name, "count": 0, "has_more": True},
            )
        else:
            NotificationService(db).create(
                "story", "info",
                f"No new stories found in r/{sub_name} (all already fetched)",
                {"subreddit": sub_name, "count": 0},
            )
    else:
        story_word = "story" if len(stories) == 1 else "stories"
        NotificationService(db).create(
            "story", "success",
            f"Fetched {len(stories)} new {story_word} from r/{sub_name}",
            {"subreddit": sub_name, "count": len(stories)},
        )


router.include_router(automation_router, prefix="/automation", tags=["Automation"])
