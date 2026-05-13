"""Story fetching with deduplication, sanitization, and update-link triggering."""

import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional

import httpx
from sqlalchemy.orm import Session

from models import Story, Subreddit, StoryStatus
from reddit.client import RedditClient, RedditClientError, RateLimitError


class SubredditAccessError(ValueError):
    """Raised when a subreddit cannot be accessed."""
    def __init__(self, message: str, is_private: bool = False):
        self.is_private = is_private
        super().__init__(message)


def sanitize_subreddit_name(name: str) -> str:
    """Normalize and validate subreddit names to prevent injection."""
    name = name.strip().lower()

    # Strip URLs and prefixes
    name = re.sub(r"^(https?://)?(www\.)?reddit\.com/r/", "", name)
    name = re.sub(r"^r/", "", name)

    # Drop trailing path/query junk
    name = name.split("/")[0].split("?")[0]

    # Reddit allows a-z, 0-9, underscore; max 21 chars (we only validate chars here)
    if not re.match(r"^[a-z0-9_]+$", name):
        raise ValueError(f"Invalid subreddit name: {name!r}")

    return name


class StoryFetcher:
    def __init__(self, db: Session):
        self.db = db
        self.client = RedditClient(db)

    def test_subreddit_access(self, name: str) -> dict:
        """Quick lightweight check if a subreddit is accessible."""
        url = f"{self.client.BASE_URL}/r/{name}/.json"
        try:
            resp = httpx.get(
                url,
                headers={"User-Agent": self.client._next_ua()},
                timeout=5.0,
                follow_redirects=True,
            )
            if resp.status_code == 403:
                # Try about page to distinguish private vs banned
                try:
                    about_url = f"{self.client.BASE_URL}/r/{name}/about/.json"
                    about_resp = httpx.get(
                        about_url,
                        headers={"User-Agent": self.client._next_ua()},
                        timeout=5.0,
                        follow_redirects=True,
                    )
                    if about_resp.status_code == 200:
                        about_data = about_resp.json()
                        sub_type = about_data.get("data", {}).get("subreddit_type")
                        if sub_type == "private":
                            return {
                                "accessible": False,
                                "is_private": True,
                                "message": f"r/{name} is a private subreddit",
                            }
                except Exception:
                    pass
                return {
                    "accessible": False,
                    "is_private": False,
                    "message": f"r/{name} may be private, banned, or restricted",
                }
            elif resp.status_code == 404:
                return {
                    "accessible": False,
                    "is_private": False,
                    "message": f"r/{name} not found",
                }
            elif resp.status_code == 429:
                return {
                    "accessible": False,
                    "is_private": False,
                    "message": f"r/{name} check blocked by rate limit. Wait and retry.",
                }
            elif resp.status_code == 200:
                return {"accessible": True, "is_private": False, "message": None}
            else:
                return {
                    "accessible": False,
                    "is_private": False,
                    "message": f"r/{name} returned HTTP {resp.status_code}",
                }
        except httpx.TimeoutException:
            return {
                "accessible": False,
                "is_private": False,
                "message": f"r/{name} check timed out",
            }
        except Exception as exc:
            return {
                "accessible": False,
                "is_private": False,
                "message": str(exc),
            }

    def add_subreddit(self, name: str, fetch_settings: Dict[str, Any] = None, force: bool = False) -> Subreddit:
        sanitized = sanitize_subreddit_name(name)

        existing = self.db.query(Subreddit).filter(Subreddit.name == sanitized).first()
        if existing:
            return existing

        if not force:
            access_check = self.test_subreddit_access(sanitized)
            if not access_check["accessible"]:
                raise SubredditAccessError(
                    access_check["message"],
                    is_private=access_check.get("is_private", False),
                )

        sub = Subreddit(
            name=sanitized,
            display_name=f"r/{sanitized}",
            fetch_settings=fetch_settings
            or {"sort": "top", "time_filter": "week", "limit": 25},
        )
        self.db.add(sub)
        self.db.commit()
        self.db.refresh(sub)
        return sub

    def fetch_stories(self, subreddit_id: int, batch_size: int = 25) -> Tuple[List[Story], Dict[str, Any]]:
        """Fetch new stories from a subreddit, resuming from last position.

        Returns: (new_stories, metadata) where metadata includes pagination info.
        """
        sub = self.db.query(Subreddit).filter(Subreddit.id == subreddit_id).first()
        if not sub:
            raise ValueError(f"Subreddit id={subreddit_id} not found")

        settings = sub.fetch_settings or {}
        sort = settings.get("sort", "top")
        time_filter = settings.get("time_filter", "week")
        limit = settings.get("limit", 25)

        # Get the last fetched story ID for pagination (stored in fetch_settings)
        last_after = settings.get("last_after", None)

        # Check rate limit before making request
        rate_limit = self.client.get_rate_limit_status()
        if rate_limit.is_exhausted:
            reset_in = int(rate_limit.reset_in_seconds)
            raise RateLimitError(
                f"Rate limit exhausted. Reset in {reset_in} seconds."
            )

        submissions, next_after = self.client.fetch_subreddit_stories(
            sub.name, sort=sort, time_filter=time_filter, limit=batch_size, after=last_after
        )

        stories: List[Story] = []
        skipped_count = 0
        for submission in submissions:
            # Deduplication: never fetch the same reddit_id twice
            exists = (
                self.db.query(Story).filter(Story.reddit_id == submission.id).first()
            )
            if exists:
                skipped_count += 1
                continue

            story = Story(
                reddit_id=submission.id,
                title=submission.title,
                author=submission.author,
                subreddit=sub.name,
                score=submission.score,
                body=submission.selftext if submission.is_self else None,
                url=submission.url,
                permalink=f"https://reddit.com{submission.permalink}",
                created_utc=datetime.fromtimestamp(submission.created_utc, tz=timezone.utc),
                status=StoryStatus.STORED.value,
            )
            self.db.add(story)
            stories.append(story)

        # Update pagination state in subreddit settings
        if stories:
            # Only update "after" if we actually fetched new stories
            sub.fetch_settings = {
                **settings,
                "last_after": next_after,
                "has_more_pages": next_after is not None,
            }
            self.db.commit()
            # Trigger update linking for this subreddit
            self._link_updates_for_subreddit(sub.name)
        elif next_after and skipped_count > 0:
            # All stories in this batch were already fetched, but there are more pages
            # Update after to skip this batch and try next
            sub.fetch_settings = {
                **settings,
                "last_after": next_after,
                "has_more_pages": next_after is not None,
            }
            self.db.commit()

        metadata = {
            "fetched": len(stories),
            "skipped": skipped_count,
            "has_more": next_after is not None,
            "rate_limit_remaining": rate_limit.remaining,
            "next_after": next_after,
        }

        return stories, metadata

    def fetch_all_active(self) -> Tuple[Dict[str, List[Story]], Dict[str, str], Dict[str, Any]]:
        """Fetch from every active subreddit. Returns (results, errors, metadata)."""
        results: Dict[str, List[Story]] = {}
        errors: Dict[str, str] = {}
        metadata: Dict[str, Any] = {"total_fetched": 0, "rate_limit_info": {}}
        active = self.db.query(Subreddit).filter(Subreddit.is_active.is_(True)).all()

        # Check overall rate limit before starting batch
        rate_limit = self.client.get_rate_limit_status()
        if rate_limit.is_exhausted:
            reset_in = int(rate_limit.reset_in_seconds)
            errors["__global__"] = f"Rate limit exhausted. Reset in {reset_in} seconds."
            metadata["rate_limit_exhausted"] = True
            metadata["reset_in_seconds"] = reset_in
            return results, errors, metadata

        metadata["rate_limit_remaining"] = rate_limit.remaining
        metadata["rate_limit_near"] = rate_limit.is_near_limit

        for sub in active:
            try:
                stories, meta = self.fetch_stories(sub.id)
                results[sub.name] = stories
                metadata["total_fetched"] += len(stories)
                metadata[f"{sub.name}_meta"] = meta
            except RateLimitError as exc:
                results[sub.name] = []
                errors[sub.name] = str(exc)
                metadata["rate_limit_exhausted"] = True
                metadata["reset_in_seconds"] = int(rate_limit.reset_in_seconds)
                break  # Stop processing further subreddits
            except Exception as exc:
                results[sub.name] = []
                errors[sub.name] = str(exc)

        return results, errors, metadata

    def reset_subreddit_pagination(self, subreddit_name: str) -> None:
        """Reset pagination for a subreddit so next fetch starts from the top."""
        sub = self.db.query(Subreddit).filter(Subreddit.name == subreddit_name).first()
        if sub and sub.fetch_settings:
            sub.fetch_settings = {
                **sub.fetch_settings,
                "last_after": None,
                "has_more_pages": True,
            }
            self.db.commit()

    def get_rate_limit_preview(self, subreddit_count: int, batch_size: int = 25) -> Dict[str, Any]:
        """Preview how many requests we can make before hitting rate limit."""
        rate_limit = self.client.get_rate_limit_status()
        requests_needed = subreddit_count  # One request per subreddit

        can_complete_all = rate_limit.remaining >= requests_needed
        partial_count = 0

        if not can_complete_all and rate_limit.remaining > 0:
            # Calculate how many stories we can fetch with remaining requests
            partial_count = rate_limit.remaining * batch_size

        return {
            "requests_remaining": rate_limit.remaining,
            "requests_needed": requests_needed,
            "can_complete_all": can_complete_all,
            "will_be_exhausted": not can_complete_all,
            "partial_fetch_possible": not can_complete_all and rate_limit.remaining > 0,
            "partial_story_count": partial_count,
            "reset_in_seconds": int(rate_limit.reset_in_seconds),
            "is_near_limit": rate_limit.is_near_limit,
        }

    def _link_updates_for_subreddit(self, subreddit_name: str) -> None:
        from reddit.linker import UpdateLinker

        linker = UpdateLinker(self.db)
        linker.link_updates_for_subreddit(subreddit_name)