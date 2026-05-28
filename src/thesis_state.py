"""
Thesis State Tracker
====================
Cross-section state tracking for multi-section coherent writing.
Tracks claims, contradictions, and section metadata across the writing process.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from enum import Enum


class SectionStatus(Enum):
    """Status of a section in the writing pipeline."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    REWRITE = "rewrite"
    VERIFIED = "verified"
    ESCALATED = "escalated"


@dataclass
class Claim:
    """A single claim made in the text, traceable to a chunk."""
    content: str
    chunk_id: int
    section: str
    used_at: datetime = field(default_factory=datetime.now)


@dataclass
class SectionMetadata:
    """Metadata for a single section."""
    title: str
    prompt: str
    generated_at: datetime = field(default_factory=datetime.now)
    rewrites_used: int = 0
    final_prose: Optional[str] = None
    status: SectionStatus = SectionStatus.PENDING
    claims: list[Claim] = field(default_factory=list)


@dataclass
class ContradictionRecord:
    """Record of a contradiction detected between sections."""
    section_a: str
    section_b: str
    claim_a: str
    claim_b: str
    same_chunk_id: int
    resolution: Optional[str] = None
    resolved_by_human: bool = False
    detected_at: datetime = field(default_factory=datetime.now)


@dataclass
class ThesisState:
    """
    Cross-section state tracker for multi-section coherent writing.

    Tracks:
    - All sections (pending, in_progress, verified)
    - Claims made per section (for contradiction detection)
    - Cross-section contradictions
    - Current section being processed
    """

    # Thesis-level info
    thesis_statement: str = ""
    dissertation_title: str = ""

    # Section tracking
    sections: dict[str, SectionMetadata] = field(default_factory=dict)
    verified_sections: list[str] = field(default_factory=list)  # Ordered list of passed section IDs
    section_order: list[str] = field(default_factory=list)  # Planned order

    # Claim registry for contradiction detection
    claims: list[Claim] = field(default_factory=list)

    # Contradiction log
    contradictions: list[ContradictionRecord] = field(default_factory=list)

    # Active section being processed
    current_section: Optional[str] = None

    # Generation stats
    total_rewrites: int = 0
    total_sections: int = 0

    def init_section(self, section_id: str, title: str, prompt: str):
        """Initialize a new section."""
        if section_id not in self.sections:
            self.sections[section_id] = SectionMetadata(title=title, prompt=prompt)
            if section_id not in self.section_order:
                self.section_order.append(section_id)
            self.total_sections += 1

    def set_current_section(self, section_id: str):
        """Set the currently active section."""
        self.current_section = section_id
        if section_id in self.sections:
            self.sections[section_id].status = SectionStatus.IN_PROGRESS

    def register_claim(self, content: str, chunk_id: int):
        """Add a claim to the registry."""
        if not self.current_section:
            return

        claim = Claim(content=content, chunk_id=chunk_id, section=self.current_section)
        self.claims.append(claim)

        if self.current_section in self.sections:
            self.sections[self.current_section].claims.append(claim)

    def check_contradiction(self, new_claim_content: str, new_chunk_id: int) -> Optional[ContradictionRecord]:
        """
        Check if new claim contradicts existing claims across sections.

        Args:
            new_claim_content: The text of the new claim
            new_chunk_id: The chunk ID the new claim cites

        Returns:
            ContradictionRecord if contradiction detected, None otherwise
        """
        # Simple contradiction: same chunk used for opposing claims
        for existing in self.claims:
            if existing.section == self.current_section:
                continue

            # Same chunk, different section
            if existing.chunk_id == new_chunk_id:
                # Check semantic opposition
                if self._detect_opposition(existing.content, new_claim_content):
                    record = ContradictionRecord(
                        section_a=existing.section,
                        section_b=self.current_section,
                        claim_a=existing.content,
                        claim_b=new_claim_content,
                        same_chunk_id=new_chunk_id
                    )
                    self.contradictions.append(record)
                    return record

        return None

    def _detect_opposition(self, claim_a: str, claim_b: str) -> bool:
        """
        Detect if two claims are semantically opposing.

        Basic heuristic: one is positive, one is negative about same subject.
        """
        neg_patterns = [
            "never", "not ", "no ", "doesn't", "isn't", "wasn't",
            "cannot", "unable", "no evidence", "doesn't appear",
            "fails to", "refuses to"
        ]

        # Check for negation patterns
        has_neg_a = any(p in claim_a.lower() for p in neg_patterns)
        has_neg_b = any(p in claim_b.lower() for p in neg_patterns)

        # If one has negation and other doesn't, might be opposing
        if has_neg_a != has_neg_b:
            # Check if they're about similar topics (basic keyword overlap)
            words_a = set(claim_a.lower().split())
            words_b = set(claim_b.lower().split())
            # Remove common words
            common = words_a & words_b
            if len(common) >= 3:  # Significant overlap
                return True

        return False

    def mark_section_verified(self, section_id: str, final_prose: str):
        """Mark a section as verified with its final prose."""
        if section_id in self.sections:
            self.sections[section_id].status = SectionStatus.VERIFIED
            self.sections[section_id].final_prose = final_prose

        if section_id not in self.verified_sections:
            self.verified_sections.append(section_id)

    def mark_section_rewrite(self, section_id: str):
        """Mark a section as needing rewrite."""
        if section_id in self.sections:
            self.sections[section_id].status = SectionStatus.REWRITE
            self.sections[section_id].rewrites_used += 1
            self.total_rewrites += 1

    def mark_section_escalated(self, section_id: str):
        """Mark a section as escalated to human."""
        if section_id in self.sections:
            self.sections[section_id].status = SectionStatus.ESCALATED

    def get_unverified_claims(self) -> list[Claim]:
        """Get claims not yet in verified sections."""
        return [
            c for c in self.claims
            if c.section not in self.verified_sections
        ]

    def get_section_claims(self, section_id: str) -> list[Claim]:
        """Get all claims for a specific section."""
        return [c for c in self.claims if c.section == section_id]

    def get_contradictions_for_section(self, section_id: str) -> list[ContradictionRecord]:
        """Get all contradictions involving a section."""
        return [
            c for c in self.contradictions
            if c.section_a == section_id or c.section_b == section_id
        ]

    def resolve_contradiction(self, index: int, resolution: str):
        """Resolve a contradiction with human decision."""
        if 0 <= index < len(self.contradictions):
            self.contradictions[index].resolution = resolution
            self.contradictions[index].resolved_by_human = True

    def get_progress_summary(self) -> dict:
        """Get a summary of writing progress."""
        verified = len(self.verified_sections)
        total = len(self.sections)
        rewrites = self.total_rewrites

        return {
            "sections_verified": verified,
            "sections_total": total,
            "progress_percent": (verified / total * 100) if total > 0 else 0,
            "total_rewrites": rewrites,
            "contradictions_pending": len([c for c in self.contradictions if not c.resolved_by_human]),
            "current_section": self.current_section
        }

    def __str__(self) -> str:
        """Human-readable summary."""
        progress = self.get_progress_summary()
        return (
            f"ThesisState: {progress['sections_verified']}/{progress['sections_total']} sections verified, "
            f"{progress['total_rewrites']} rewrites, {progress['contradictions_pending']} pending contradictions"
        )


def create_thesis_state(
    thesis_statement: str = "",
    dissertation_title: str = "",
    section_order: list[str] = None
) -> ThesisState:
    """
    Factory function to create a new ThesisState.

    Args:
        thesis_statement: The main thesis statement
        dissertation_title: Title of the dissertation
        section_order: Ordered list of section IDs to write

    Returns:
        ThesisState instance
    """
    state = ThesisState(
        thesis_statement=thesis_statement,
        dissertation_title=dissertation_title
    )

    if section_order:
        for section_id in section_order:
            state.section_order.append(section_id)

    return state