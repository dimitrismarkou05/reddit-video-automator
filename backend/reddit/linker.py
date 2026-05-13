"""Update detection and parent-story linking algorithm.

Handles two types of updates:
1. SEPARATE POSTS: A user creates a new post with "Update", "Part 2", etc. in the title.
   These are linked to the original post via title similarity matching.
2. INLINE EDITS: The user edits the original post body to add "UPDATE" or "Part 2" sections.
   These are detected by scanning the body text for update markers and splitting the content.
"""

import re
from typing import List, Optional, Tuple
from dataclasses import dataclass

from sqlalchemy import and_
from sqlalchemy.orm import Session

from models import Story, StoryStatus


# Keywords that indicate a separate post is an update to a previous post
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

# Patterns that indicate inline update sections within a post body.
# Designed to avoid overlapping matches — e.g. "UPDATE:" won't match "UPDATE 1:"
INLINE_UPDATE_PATTERNS = [
    # "UPDATE" or "UPDATED" standalone — must NOT be followed by digits
    r'(?:^|\n)\s*(?:UPDATE|UPDATED)(?!\s*\d)\s*(?::|—|-)?\s*',
    # "UPDATE 1", "UPDATE 2", etc. — explicitly requires digits
    r'(?:^|\n)\s*(?:UPDATE|UPDATED)\s+\d+\s*(?::|—|-)?\s*',
    # "Part 2", "Part 3", etc. at start of line
    r'(?:^|\n)\s*(?:PART|Part)\s+(?:2|3|4|5|two|three|four|five)\s*(?::|—|-)?\s*',
    # "Pt 2", "Pt. 2", etc.
    r'(?:^|\n)\s*(?:PT|Pt)\.?\s+(?:2|3|4|5|two|three|four|five)\s*(?::|—|-)?\s*',
    # "EDIT:" or "EDIT -" — must NOT be followed by digits
    r'(?:^|\n)\s*(?:EDIT|EDITS)(?!\s*\d)\s*(?::|—|-)?\s*',
    # "EDIT 1:", "EDIT 2:", etc.
    r'(?:^|\n)\s*(?:EDIT|EDITS)\s+\d+\s*(?::|—|-)?\s*',
    # "Final Update", "Final Update:" 
    r'(?:^|\n)\s*(?:FINAL\s+UPDATE|Final\s+Update)\s*(?::|—|-)?\s*',
    # "**Update**" or "__Update__" (markdown bold/italic)
    r'(?:^|\n)\s*(?:\*\*|__)?\s*(?:UPDATE|UPDATED)\s*(?:\*\*|__)?\s*(?::|—|-)?\s*',
    # Numbered update sections like "1. Update" or "Update 1:"
    r'(?:^|\n)\s*\d+\.\s*(?:UPDATE|UPDATED)\s*(?::|—|-)?\s*',
    # "UPDATE -" or "UPDATE —" with dash
    r'(?:^|\n)\s*(?:UPDATE|UPDATED)\s*[\-–—]\s*',
]

# Compile patterns for performance
INLINE_UPDATE_REGEXES = [re.compile(pattern, re.IGNORECASE) for pattern in INLINE_UPDATE_PATTERNS]


@dataclass
class InlineUpdateSection:
    """Represents an inline update section found within a post body."""
    marker: str           # The raw marker text found (e.g., "UPDATE:")
    content: str          # The content following the marker
    position: int         # Character position in the original body
    section_index: int    # Which section number this is (0 = original, 1+ = updates)


class UpdateLinker:
    def __init__(self, db: Session):
        self.db = db

    # ───────────────────────────────────────────────────────────────
    # SEPARATE POST UPDATE DETECTION (existing logic, refined)
    # ───────────────────────────────────────────────────────────────

    def _is_likely_update(self, story: Story) -> bool:
        """Check if a story's title suggests it's a separate update post."""
        title_lower = story.title.lower()
        for keyword in UPDATE_KEYWORDS:
            if keyword in title_lower:
                return True
        if re.search(r"[\[\(]?\s*update\s*[\]\)]?", title_lower):
            return True
        return False

    def _find_original_story(self, update_story: Story) -> Optional[Story]:
        """Find the original story that a separate update post refers to."""
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

    # ───────────────────────────────────────────────────────────────
    # INLINE UPDATE DETECTION (new logic)
    # ───────────────────────────────────────────────────────────────

    def _find_inline_update_markers(self, body: str) -> List[Tuple[int, str]]:
        """
        Scan post body for inline update markers.
        Returns list of (position, marker_text) tuples sorted by position.
        """
        if not body:
            return []

        markers: List[Tuple[int, str]] = []
        seen_positions = set()

        for regex in INLINE_UPDATE_REGEXES:
            for match in regex.finditer(body):
                pos = match.start()
                # Avoid duplicate markers at same position
                if pos not in seen_positions:
                    seen_positions.add(pos)
                    markers.append((pos, match.group().strip()))

        # Sort by position in text
        markers.sort(key=lambda x: x[0])
        return markers

    def _split_body_into_sections(self, story: Story) -> List[InlineUpdateSection]:
        """
        Split a post body into original + inline update sections.
        Returns empty list if no inline updates found.
        """
        if not story.body:
            return []

        markers = self._find_inline_update_markers(story.body)
        if not markers:
            return []

        sections: List[InlineUpdateSection] = []

        # First section: from start of body to first marker
        first_marker_pos = markers[0][0]
        original_content = story.body[:first_marker_pos].strip()

        if original_content:
            sections.append(InlineUpdateSection(
                marker="ORIGINAL",
                content=original_content,
                position=0,
                section_index=0,
            ))

        # Subsequent sections: between markers
        for i, (pos, marker_text) in enumerate(markers):
            # Find where this section ends (start of next marker or end of body)
            if i + 1 < len(markers):
                end_pos = markers[i + 1][0]
            else:
                end_pos = len(story.body)

            content = story.body[pos:end_pos].strip()
            # Remove the marker itself from the content
            content = content[len(marker_text):].strip()
            # Clean up leading punctuation
            content = re.sub(r'^[\s:—\-]+', '', content)

            if content:
                sections.append(InlineUpdateSection(
                    marker=marker_text,
                    content=content,
                    position=pos,
                    section_index=i + 1,
                ))

        return sections

    def _has_inline_updates(self, story: Story) -> bool:
        """Quick check if a story body contains inline update markers."""
        if not story.body:
            return False
        return len(self._find_inline_update_markers(story.body)) > 0

    def _count_inline_updates(self, story: Story) -> int:
        """Count how many inline update sections exist in a story body."""
        return len(self._find_inline_update_markers(story.body))

    # ───────────────────────────────────────────────────────────────
    # PUBLIC API
    # ───────────────────────────────────────────────────────────────

    def link_updates_for_subreddit(self, subreddit_name: str) -> int:
        """
        Scan unlinked stories and:
        1. Link separate update posts to their original posts (existing logic)
        2. Detect inline updates within post bodies and mark them (new logic)

        Returns total count of linked/identified updates.
        """
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
        inline_detected_count = 0

        for story in unlinked:
            # ── Case 1: Separate update post ──
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
                    continue  # This story is handled, move to next

            # ── Case 2: Inline updates in body ──
            if self._has_inline_updates(story):
                inline_count = self._count_inline_updates(story)
                story.update_reason = (
                    f"Contains {inline_count} inline update section(s) "
                    f"in post body (reddit_id={story.reddit_id})"
                )
                # Note: We don't set is_update=True here because the original post
                # IS the original — it just contains updates within it.
                # The frontend/pipeline can use update_reason to know it has inline updates.
                inline_detected_count += 1

        if linked_count or inline_detected_count:
            self.db.commit()

        return linked_count + inline_detected_count

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

    def get_inline_sections(self, story_id: int) -> List[InlineUpdateSection]:
        """
        Get inline update sections for a story.
        Returns empty list if the story has no inline updates.
        """
        story = self.db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return []
        return self._split_body_into_sections(story)

    def get_full_narrative(self, story_id: int, include_inline_updates: bool = True) -> str:
        """
        Build the full narrative text for a story, including:
        - The original story
        - Any linked separate update posts
        - Any inline update sections (if include_inline_updates=True)

        This is useful for the video generation pipeline.
        """
        story = self.db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return ""

        parts = []

        # Add original story
        parts.append(f"{story.title}. {story.body or ''}")

        # Add linked separate updates
        if story.updates:
            chain = self.get_story_chain(story.id)
            for update in chain[1:]:
                parts.append(f"Update. {update.title}. {update.body or ''}")

        # Add inline update sections
        if include_inline_updates:
            inline_sections = self._split_body_into_sections(story)
            if len(inline_sections) > 1:
                for section in inline_sections[1:]:
                    parts.append(f"{section.marker} {section.content}")

        return "\n\n".join(parts)