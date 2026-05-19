"""Regex patterns and keywords for update detection."""

import re

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
    r'(?:^|)\s*(?:\*\*|__)?\s*UPDATE(?!D)\b\s*(?::|—|-)?\s*',
    # "UPDATE 1", "UPDATE 2", etc. — with number
    r'(?:^|)\s*(?:\*\*|__)?\s*UPDATE\s+\d+\s*(?::|—|-)?\s*',
    # "Part 2", "Part 3", etc. at start of line
    r'(?:^|)\s*(?:\*\*|__)?\s*(?:PART|Part)\s+(?:2|3|4|5|two|three|four|five)\s*(?::|—|-)?\s*',
    # "Pt 2", "Pt. 2", etc.
    r'(?:^|)\s*(?:\*\*|__)?\s*(?:PT|Pt)\.?\s+(?:2|3|4|5|two|three|four|five)\s*(?::|—|-)?\s*',
    # "EDIT:" or "EDIT -" — must NOT be followed by digits
    r'(?:^|)\s*(?:\*\*|__)?\s*(?:EDIT|EDITS)(?!\s*\d)\s*(?::|—|-)?\s*',
    # "EDIT 1:", "EDIT 2:", etc.
    r'(?:^|)\s*(?:\*\*|__)?\s*(?:EDIT|EDITS)\s+\d+\s*(?::|—|-)?\s*',
    # "Final Update", "Final Update:"
    r'(?:^|)\s*(?:\*\*|__)?\s*(?:FINAL\s+UPDATE|Final\s+Update)\s*(?::|—|-)?\s*',
    # Numbered update sections like "1. Update" or "Update 1:"
    r'(?:^|)\s*\d+\.\s*(?:\*\*|__)?\s*UPDATE\s*(?::|—|-)?\s*',
    # "UPDATE -" or "UPDATE —" with dash
    r'(?:^|)\s*(?:\*\*|__)?\s*UPDATE\s*[\-–—]\s*',
    # "**UPDATE**" or "__UPDATE__" (markdown bold/italic) — standalone
    r'(?:^|)\s*(?:\*\*|__)\s*UPDATE\s*(?:\*\*|__)\s*(?::|—|-)?\s*',
]

# Compile patterns for performance
INLINE_UPDATE_REGEXES = [re.compile(pattern, re.IGNORECASE) for pattern in INLINE_UPDATE_PATTERNS]

# Pattern to detect "UPDATED" at the very beginning of a post
# This indicates the post contains inline updates but is NOT itself a section marker
UPDATED_PREFIX_PATTERN = re.compile(
    r'^\s*UPDATED\s*(?::|—|-)?\s*',
    re.IGNORECASE
)
