"""Update detection and parent-story linking algorithm."""

import re
from typing import List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from models import Story, StoryStatus


UPDATE_KEYWORDS = [
    "update",
    "follow-up",
    "follow up",
    "followup",
    "part 2",
    "part 3",
    "part 4",
    "part 5",
    "pt 2",
    "pt. 2",
    "pt 3",
    "pt. 3",
    "part two",
    "part three",
    "final update",
    "update to",
]


class UpdateLinker:
    def __init__(self, db: Session):
        self.db = db

    def _is_likely_update(self, story: Story) -> bool:
        title_lower = story.title.lower()
        for keyword in UPDATE_KEYWORDS:
            if keyword in title_lower:
                return True
        if re.search(r"[\[\(]?\s*update\s*[\]\)]?", title_lower):
            return True
        return False

    def _find_original_story(self, update_story: Story) -> Optional[Story]:
        if not self._is_likely_update(update_story):
            return None

        # Candidates: same author, same subreddit, older, not already an update
        candidates = (
            self.db.query(Story)
            .filter(
                and_(
                    Story.author == update_story.author,
                    Story.subreddit == update_story.subreddit,
                    Story.is_update.is_(False),
                    Story.created_utc < update_story.created_utc,
                    Story.id != update_story.id,
                )
            )
            .order_by(Story.created_utc.desc())
            .all()
        )

        if not candidates:
            return None

        # Build a normalized core title by stripping update keywords
        core_title = update_story.title.lower()
        for keyword in UPDATE_KEYWORDS:
            core_title = core_title.replace(keyword, "")
        core_title = re.sub(r"[^\w\s]", "", core_title).strip()
        core_words = set(core_title.split())

        best_match: Optional[Story] = None
        best_score = 0.0

        for candidate in candidates:
            cand_title = re.sub(r"[^\w\s]", "", candidate.title.lower()).strip()
            cand_words = set(cand_title.split())

            if not core_words or not cand_words:
                continue

            overlap = len(core_words & cand_words)
            score = overlap / max(len(core_words), len(cand_words))

            if score > 0.5 and score > best_score:
                best_score = score
                best_match = candidate

        # Fallback: if strong keyword match but only one candidate exists
        if not best_match and len(candidates) == 1:
            best_match = candidates[0]

        return best_match

    def link_updates_for_subreddit(self, subreddit_name: str) -> int:
        """Scan unlinked stories and attach updates to originals. Returns count linked."""
        unlinked = (
            self.db.query(Story)
            .filter(
                and_(
                    Story.subreddit == subreddit_name,
                    Story.is_update.is_(False),
                    Story.parent_story_id.is_(None),
                )
            )
            .all()
        )

        linked_count = 0
        for story in unlinked:
            if self._is_likely_update(story):
                original = self._find_original_story(story)
                if original:
                    story.parent_story_id = original.id
                    story.is_update = True
                    story.update_reason = (
                        f"Linked to original '{original.title[:60]}...' "
                        f"(reddit_id={original.reddit_id})"
                    )
                    story.status = StoryStatus.UPDATE_LINKED.value
                    linked_count += 1

        if linked_count:
            self.db.commit()

        return linked_count

    def get_story_chain(self, story_id: int) -> List[Story]:
        """Return original + all updates in chronological order."""
        story = self.db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return []

        # If user passed an update id, walk up to the original
        root = story
        while root.parent_story_id is not None:
            root = root.parent_story

        chain = [root]
        chain.extend(sorted(root.updates, key=lambda s: s.created_utc))
        return chain