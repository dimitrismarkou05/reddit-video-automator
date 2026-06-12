"""Update detection and parent-story linking algorithm."""

import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from stories.models import Story, StoryStatus
from stories.linker.models import InlineUpdateSection
from stories.linker.patterns import (
    UPDATE_KEYWORDS,
    INLINE_UPDATE_REGEXES,
    UPDATED_PREFIX_PATTERN,
)


class UpdateLinker:
    """Scans stories and links updates (separate posts and inline sections)."""

    def __init__(self, db: Session):
        self.db = db

    #    Separate Post Detection                                         

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

        if not best_match and len(candidates) == 1:
            best_match = candidates[0]

        return best_match

    #    Inline Update Detection                                         

    def _strip_updated_prefix(self, body: str) -> Tuple[str, bool, int]:
        """Strip 'UPDATED' prefix from the beginning of the body if present."""
        if not body:
            return body, False, 0

        match = UPDATED_PREFIX_PATTERN.match(body)
        if match:
            cleaned = body[match.end():].lstrip()
            return cleaned, True, match.end()
        return body, False, 0

    def _find_inline_update_markers(self, body: str) -> List[Tuple[int, str]]:
        """Scan post body for inline update markers."""
        if not body:
            return []

        cleaned_body, had_prefix, prefix_offset = self._strip_updated_prefix(body)

        markers: List[Tuple[int, str]] = []
        seen_positions = set()

        for regex in INLINE_UPDATE_REGEXES:
            for match in regex.finditer(cleaned_body):
                pos = match.start() + prefix_offset
                if pos not in seen_positions:
                    seen_positions.add(pos)
                    markers.append((pos, match.group().strip()))

        markers.sort(key=lambda x: x[0])
        return markers

    def _split_body_into_sections(self, story: Story) -> List[InlineUpdateSection]:
        """Split a post body into original + inline update sections."""
        if not story.body:
            return []

        markers = self._find_inline_update_markers(story.body)
        if not markers:
            return []

        sections: List[InlineUpdateSection] = []

        first_marker_pos = markers[0][0]
        original_content = story.body[:first_marker_pos].strip()
        original_content, _, _ = self._strip_updated_prefix(original_content)

        if original_content:
            sections.append(InlineUpdateSection(
                marker="ORIGINAL",
                content=original_content,
                position=0,
                section_index=0,
            ))

        for i, (pos, marker_text) in enumerate(markers):
            if i + 1 < len(markers):
                end_pos = markers[i + 1][0]
            else:
                end_pos = len(story.body)

            content = story.body[pos:end_pos].strip()
            content = content[len(marker_text):].strip()
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

    def _create_inline_update_story(
        self,
        original: Story,
        section: InlineUpdateSection,
        update_number: int,
    ) -> Story:
        """Create a child Story record from an inline update section."""
        synthetic_reddit_id = f"{original.reddit_id}_inline_{update_number}"

        content_first_line = section.content.split('\n')[0].strip()
        if len(content_first_line) > 80:
            content_first_line = content_first_line[:77] + "..."

        title = (
            f"Update {update_number}: {content_first_line}"
            if update_number > 1
            else f"Update: {content_first_line}"
        )

        update_story = Story(
            reddit_id=synthetic_reddit_id,
            title=title,
            author=original.author,
            subreddit=original.subreddit,
            score=original.score,
            body=section.content,
            url=original.url,
            permalink=original.permalink,
            created_utc=original.created_utc,
            fetched_at=datetime.now(timezone.utc),
            status=StoryStatus.UPDATE_LINKED.value,
            parent_story_id=original.id,
            is_update=True,
            update_reason=f"Inline update section #{update_number} from original post (marker: '{section.marker}')",
        )

        self.db.add(update_story)
        return update_story

    #    Public API                                                      

    def link_updates_for_subreddit(self, subreddit_name: str) -> int:
        """
        Scan unlinked stories and link separate update posts + detect inline updates.
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
            # Case 1: Separate update post
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
                    continue

            # Case 2: Inline updates in body
            if self._has_inline_updates(story):
                sections = self._split_body_into_sections(story)
                update_sections = [s for s in sections if s.section_index > 0]

                for i, section in enumerate(update_sections, start=1):
                    existing = (
                        self.db.query(Story)
                        .filter(Story.reddit_id == f"{story.reddit_id}_inline_{i}")
                        .first()
                    )
                    if not existing:
                        self._create_inline_update_story(story, section, i)
                        inline_created_count += 1

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

        root = story
        while root.parent_story_id is not None:
            root = root.parent_story

        chain = [root]
        chain.extend(sorted(root.updates, key=lambda s: s.created_utc))
        return chain

    def get_inline_sections(self, story_id: int) -> List[InlineUpdateSection]:
        """Get inline update sections for a story."""
        story = self.db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return []
        return self._split_body_into_sections(story)

    def get_full_narrative(self, story_id: int, include_inline_updates: bool = True) -> str:
        """Build the full narrative text for a story, including all updates."""
        story = self.db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return ""

        parts = []

        body, had_prefix, _ = self._strip_updated_prefix(story.body or "")
        parts.append(f"{story.title}. {body}")

        if story.updates:
            chain = self.get_story_chain(story.id)
            for update in chain[1:]:
                parts.append(f"Update. {update.title}. {update.body or ''}")

        if include_inline_updates:
            inline_sections = self._split_body_into_sections(story)
            if len(inline_sections) > 1:
                for section in inline_sections[1:]:
                    parts.append(f"{section.marker} {section.content}")

        return "\n\n".join(parts)
