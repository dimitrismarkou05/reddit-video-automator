"""Update detection and parent-story linking algorithm.

Handles two types of updates:
1. SEPARATE POSTS: A user creates a new post with "Update", "Part 2", etc. in the title.
   These are linked to the original post via title similarity matching.
2. INLINE EDITS: The user edits the original post body to add "UPDATE" or "Part 2" sections.
   These are detected by scanning the body text for update markers, splitting the content,
   and creating child Story records for each inline update section.
"""

import re
from datetime import datetime, timezone
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

INLINE_UPDATE_PATTERNS = [
    # "UPDATE" standalone at line start — NOT "UPDATED"
    # Negative lookahead for "D" to avoid matching "UPDATED"
    r'(?:^|\n)\s*(?:\*\*|__)?\s*UPDATE(?!D)\b\s*(?::|—|-)?\s*',
    # "UPDATE 1", "UPDATE 2", etc. — with number
    r'(?:^|\n)\s*(?:\*\*|__)?\s*UPDATE\s+\d+\s*(?::|—|-)?\s*',
    # "Part 2", "Part 3", etc. at start of line
    r'(?:^|\n)\s*(?:\*\*|__)?\s*(?:PART|Part)\s+(?:2|3|4|5|two|three|four|five)\s*(?::|—|-)?\s*',
    # "Pt 2", "Pt. 2", etc.
    r'(?:^|\n)\s*(?:\*\*|__)?\s*(?:PT|Pt)\.?\s+(?:2|3|4|5|two|three|four|five)\s*(?::|—|-)?\s*',
    # "EDIT:" or "EDIT -" — must NOT be followed by digits
    r'(?:^|\n)\s*(?:\*\*|__)?\s*(?:EDIT|EDITS)(?!\s*\d)\s*(?::|—|-)?\s*',
    # "EDIT 1:", "EDIT 2:", etc.
    r'(?:^|\n)\s*(?:\*\*|__)?\s*(?:EDIT|EDITS)\s+\d+\s*(?::|—|-)?\s*',
    # "Final Update", "Final Update:"
    r'(?:^|\n)\s*(?:\*\*|__)?\s*(?:FINAL\s+UPDATE|Final\s+Update)\s*(?::|—|-)?\s*',
    # Numbered update sections like "1. Update" or "Update 1:"
    r'(?:^|\n)\s*\d+\.\s*(?:\*\*|__)?\s*UPDATE\s*(?::|—|-)?\s*',
    # "UPDATE -" or "UPDATE —" with dash
    r'(?:^|\n)\s*(?:\*\*|__)?\s*UPDATE\s*[\-–—]\s*',
    # "**UPDATE**" or "__UPDATE__" (markdown bold/italic) — standalone
    r'(?:^|\n)\s*(?:\*\*|__)\s*UPDATE\s*(?:\*\*|__)\s*(?::|—|-)?\s*',
]

# Compile patterns for performance
INLINE_UPDATE_REGEXES = [re.compile(pattern, re.IGNORECASE) for pattern in INLINE_UPDATE_PATTERNS]

# Pattern to detect "UPDATED" at the very beginning of a post
# This indicates the post contains inline updates but is NOT itself a section marker
UPDATED_PREFIX_PATTERN = re.compile(
    r'^\s*UPDATED\s*(?::|—|-)?\s*',
    re.IGNORECASE
)


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
    # INLINE UPDATE DETECTION (enhanced logic)
    # ───────────────────────────────────────────────────────────────

    def _strip_updated_prefix(self, body: str) -> Tuple[str, bool, int]:
        """
        Strip 'UPDATED' prefix from the beginning of the body if present.
        Returns (cleaned_body, had_prefix, prefix_length).

        Example: 'UPDATED\n\nTl;dr...' -> ('Tl;dr...', True, 9)
        """
        if not body:
            return body, False, 0

        match = UPDATED_PREFIX_PATTERN.match(body)
        if match:
            cleaned = body[match.end():].lstrip()
            return cleaned, True, match.end()
        return body, False, 0

    def _find_inline_update_markers(self, body: str) -> List[Tuple[int, str]]:
        """
        Scan post body for inline update markers.
        Returns list of (position, marker_text) tuples sorted by position.

        NOTE: We first strip any 'UPDATED' prefix, then scan for actual
        'UPDATE' section markers within the cleaned body.
        """
        if not body:
            return []

        # Strip "UPDATED" prefix if present — it indicates the post has updates
        # but is not itself a section divider
        cleaned_body, had_prefix, prefix_offset = self._strip_updated_prefix(body)

        markers: List[Tuple[int, str]] = []
        seen_positions = set()

        for regex in INLINE_UPDATE_REGEXES:
            for match in regex.finditer(cleaned_body):
                # Adjust position to account for stripped prefix
                pos = match.start() + prefix_offset
                # Avoid duplicate markers at same position
                if pos not in seen_positions:
                    seen_positions.add(pos)
                    markers.append((pos, match.group().strip()))

        # Sort by position in original text
        markers.sort(key=lambda x: x[0])
        return markers

    def _split_body_into_sections(self, story: Story) -> List[InlineUpdateSection]:
        """
        Split a post body into original + inline update sections.
        Returns empty list if no inline updates found.

        Handles the case where the post starts with 'UPDATED' prefix:
        - 'UPDATED' at start -> stripped, not treated as a section marker
        - 'UPDATE' markers within -> treated as section dividers
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

        # Strip "UPDATED" prefix from original content if present
        original_content, _, _ = self._strip_updated_prefix(original_content)

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

    def _create_inline_update_story(
        self,
        original: Story,
        section: InlineUpdateSection,
        update_number: int,
    ) -> Story:
        """
        Create a child Story record from an inline update section.

        These synthetic stories represent update sections found within the original
        post body. They are linked to the original via parent_story_id and marked
        with is_update=True so they appear in the frontend's update branch view.
        """
        # Generate a synthetic reddit_id based on the original
        synthetic_reddit_id = f"{original.reddit_id}_inline_{update_number}"

        # Build a title from the marker and first line of content
        content_first_line = section.content.split('\n')[0].strip()
        if len(content_first_line) > 80:
            content_first_line = content_first_line[:77] + "..."

        title = f"Update {update_number}: {content_first_line}" if update_number > 1 else f"Update: {content_first_line}"

        # Use the original's metadata for author/subreddit/score
        # but use a slightly later timestamp to preserve ordering
        update_story = Story(
            reddit_id=synthetic_reddit_id,
            title=title,
            author=original.author,
            subreddit=original.subreddit,
            score=original.score,  # Same score as original (no separate upvotes)
            body=section.content,
            url=original.url,
            permalink=original.permalink,
            created_utc=original.created_utc,  # Same time as original
            fetched_at=datetime.now(timezone.utc),
            status=StoryStatus.UPDATE_LINKED.value,
            parent_story_id=original.id,
            is_update=True,
            update_reason=f"Inline update section #{update_number} from original post (marker: '{section.marker}')",
        )

        self.db.add(update_story)
        return update_story

    # ───────────────────────────────────────────────────────────────
    # PUBLIC API
    # ───────────────────────────────────────────────────────────────

    def link_updates_for_subreddit(self, subreddit_name: str) -> int:
        """
        Scan unlinked stories and:
        1. Link separate update posts to their original posts (existing logic)
        2. Detect inline updates within post bodies, create child Story records,
           and link them to the original (enhanced logic)

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
        inline_created_count = 0

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
                sections = self._split_body_into_sections(story)

                # Create child Story records for each inline update section (skip section 0 = original)
                update_sections = [s for s in sections if s.section_index > 0]

                for i, section in enumerate(update_sections, start=1):
                    # Check if this inline update was already created (avoid duplicates)
                    existing = (
                        self.db.query(Story)
                        .filter(Story.reddit_id == f"{story.reddit_id}_inline_{i}")
                        .first()
                    )
                    if not existing:
                        self._create_inline_update_story(story, section, i)
                        inline_created_count += 1

                # Update the original story's metadata
                _, had_updated_prefix, _ = self._strip_updated_prefix(story.body or "")
                prefix_note = " (has UPDATED prefix)" if had_updated_prefix else ""
                story.update_reason = (
                    f"Contains {len(update_sections)} inline update section(s){prefix_note} "
                    f"in post body (reddit_id={story.reddit_id})"
                )

        if linked_count or inline_created_count:
            self.db.commit()

        return linked_count + inline_created_count

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
        - The original story (with UPDATED prefix stripped if present)
        - Any linked separate update posts
        - Any inline update sections (if include_inline_updates=True)

        This is useful for the video generation pipeline.
        """
        story = self.db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return ""

        parts = []

        # Add original story — strip UPDATED prefix if present
        body, had_prefix, _ = self._strip_updated_prefix(story.body or "")
        parts.append(f"{story.title}. {body}")

        # Add linked separate updates and inline updates
        if story.updates:
            chain = self.get_story_chain(story.id)
            for update in chain[1:]:
                parts.append(f"Update. {update.title}. {update.body or ''}")

        # Add inline update sections (fallback if updates relationship not loaded)
        if include_inline_updates:
            inline_sections = self._split_body_into_sections(story)
            if len(inline_sections) > 1:
                for section in inline_sections[1:]:
                    parts.append(f"{section.marker} {section.content}")

        return "\n\n".join(parts)