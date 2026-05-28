"""
Write Agent
==========
Constrained writing agent that generates academic prose only from retrieved chunks.
Hard-coded constraint: every claim must be traceable to a [CHUNK-N] marker.

Architecture:
- write_section(): Generate prose from chunks
- rewrite(): Regenerate with auditor feedback
- ALL claims must cite [CHUNK-N] - no unverified claims allowed
"""

import re
import asyncio
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

from thesis_state import ThesisState


@dataclass
class WritingResult:
    """Output from write_agent.write_section()"""
    prose: str
    claim_markers: list[dict]  # [{chunk_id, start_pos, end_pos, claim_text}]
    citations: list[dict]      # [{chunk_id, author, year, title, quote}]
    has_gaps: bool = False      # True if "I don't have information" appears
    gap_phrases: list[str] = field(default_factory=list)


@dataclass
class RewriteFeedback:
    """Structured feedback from auditor for rewrite"""
    layer: int                          # Which verification layer failed
    issue: str                          # Description of issue
    fix_suggestion: str                 # How to fix
    claim_text: Optional[str] = None    # The specific claim that failed


class WriteAgent:
    """
    Constrained writing agent for academic prose generation.

    Key constraint: ONLY write claims that exist in retrieved chunks.
    Every claim MUST be traceable to a [CHUNK-N] marker.
    If claim isn't in chunks → "I don't have information about X"
    """

    def __init__(
        self,
        llm_func: callable,
        chunk_provider: callable = None  # Function to get chunk content by ID
    ):
        """
        Args:
            llm_func: Async LLM function from config.py (create_llm_func())
            chunk_provider: Optional function(chunk_id) -> str to get chunk content
        """
        self.llm_func = llm_func
        self.chunk_provider = chunk_provider

        # System prompt enforces hard constraints
        self.system_prompt = """You are an academic writing assistant.

CRITICAL CONSTRAINTS:
1. EVERY claim must be traceable to a retrieved chunk via [CHUNK-N] marker
2. If you cannot support a claim with retrieved chunks, write: "I don't have sufficient information about [topic]."
3. Do NOT make claims not supported by chunks
4. Use MLA 9th citation format for in-text citations

OUTPUT FORMAT:
- Write academic prose with [CHUNK-N] markers for each claim
- Cite sources as (Author Year) per MLA 9th
- If you must say "I don't have information", be explicit about what you lack

BAD OUTPUT (will fail verification):
"The novel shows X which is evident from the text."

GOOD OUTPUT (will pass verification):
"The novel demonstrates X [CHUNK-3] through character development, as Singh writes..."
"""

    async def write_section(
        self,
        topic: str,
        section_prompt: str,
        chunks: list[dict],
        thesis_state: ThesisState,
        style: str = "academic"
    ) -> WritingResult:
        """
        Generate a section of academic prose from retrieved chunks.

        Args:
            topic: The writing topic/section ID (e.g., "1.1 Historical Background")
            section_prompt: Detailed prompt for what to write
            chunks: List of retrieved chunks [{ref_id, content}, ...]
            thesis_state: Current thesis state for tracking
            style: Writing style (academic, formal, technical)

        Returns:
            WritingResult with prose, claim_markers, citations
        """
        # Build context from chunks
        context = self._build_chunk_context(chunks)

        # Style-specific writing instructions
        style_instructions = {
            "academic": "Write in formal academic prose. Use scholarly voice. Section length: 400-600 words.",
            "formal": "Write in formal but accessible style. Section length: 400-600 words.",
            "technical": "Write technically precise prose. Section length: 300-500 words."
        }

        prompt = f"""Write section: {topic}

{section_prompt}

Retrieved context (use these chunks, cite with [CHUNK-N]):
{context}

Style: {style_instructions.get(style, style_instructions['academic'])}

Remember:
- Every factual claim MUST cite a [CHUNK-N]
- Use (Author Year) format for MLA citations
- Write only supported claims, say "I don't have information" for unsupported topics
"""

        response = await self.llm_func(prompt, system_prompt=self.system_prompt)

        # Parse response to extract claim markers
        claim_markers = self._extract_claim_markers(response, chunks)
        citations = self._extract_citations(response, chunks)

        # Check for over-constrained fragmentation
        gap_phrases = self._detect_gaps(response)
        has_gaps = len(gap_phrases) > 0

        return WritingResult(
            prose=response,
            claim_markers=claim_markers,
            citations=citations,
            has_gaps=has_gaps,
            gap_phrases=gap_phrases
        )

    async def rewrite(
        self,
        original_prose: str,
        feedback: list[RewriteFeedback],
        chunks: list[dict],
        thesis_state: ThesisState
    ) -> WritingResult:
        """
        Rewrite prose based on auditor feedback.

        Args:
            original_prose: The prose that failed verification
            feedback: List of RewriteFeedback from auditor
            chunks: Retrieved chunks (same as original)
            thesis_state: Thesis state for tracking

        Returns:
            WritingResult with revised prose
        """
        # Build feedback context
        feedback_context = "Issues to fix:\n"
        for i, f in enumerate(feedback, 1):
            feedback_context += f"{i}. [{f.layer}] {f.issue}\n"
            feedback_context += f"   Fix: {f.fix_suggestion}\n"
            if f.claim_text:
                feedback_context += f"   Claim: {f.claim_text}\n"

        context = self._build_chunk_context(chunks)

        prompt = f"""Rewrite the following prose to fix verification issues.

ORIGINAL PROSE:
{original_prose}

{feedback_context}

Retrieved chunks (use these, cite with [CHUNK-N]):
{context}

CRITICAL:
- Fix each issue listed above
- Every claim MUST cite [CHUNK-N]
- Use MLA 9th format: (Author Year)
- Do not introduce new claims without chunk support
- Keep the same section topic and structure

Write the corrected version:
"""

        response = await self.llm_func(prompt, system_prompt=self.system_prompt)

        # Parse as before
        claim_markers = self._extract_claim_markers(response, chunks)
        citations = self._extract_citations(response, chunks)
        gap_phrases = self._detect_gaps(response)
        has_gaps = len(gap_phrases) > 0

        return WritingResult(
            prose=response,
            claim_markers=claim_markers,
            citations=citations,
            has_gaps=has_gaps,
            gap_phrases=gap_phrases
        )

    def _build_chunk_context(self, chunks: list[dict]) -> str:
        """Build context string from chunks for the prompt."""
        context = ""
        for i, chunk in enumerate(chunks):
            chunk_id = chunk.get('ref_id', str(i + 1))
            content = chunk.get('content', '')[:1000]  # Limit per chunk
            context += f"\n[CHUNK-{chunk_id}]\n{content}\n"
        return context

    def _extract_claim_markers(self, prose: str, chunks: list[dict]) -> list[dict]:
        """Extract [CHUNK-N] markers and their positions from prose."""
        markers = []
        pattern = r'\[CHUNK-(\d+)\]'

        for match in re.finditer(pattern, prose):
            chunk_id = int(match.group(1))
            start = match.start()
            end = match.end()

            # Get surrounding text as claim context (sentence containing marker)
            # Find sentence boundaries
            before = prose[:start]
            after = prose[end:]
            sentence_end = after.find('.') if after.find('.') != -1 else 50

            claim_text = prose[start:start + 100]  # Rough sentence

            markers.append({
                'chunk_id': chunk_id,
                'start_pos': start,
                'end_pos': end,
                'claim_text': claim_text.strip()
            })

        return markers

    def _extract_citations(self, prose: str, chunks: list[dict]) -> list[dict]:
        """Extract MLA 9th citations from prose."""
        citations = []

        # Find all [CHUNK-N] references
        pattern = r'\[CHUNK-(\d+)\]'
        chunk_refs = set()

        for match in re.finditer(pattern, prose):
            chunk_id = int(match.group(1))
            chunk_refs.add(chunk_id)

        # Map chunk IDs to citation info from citation_map
        for chunk_id in chunk_refs:
            # Find corresponding chunk data
            chunk_data = None
            for chunk in chunks:
                if int(chunk.get('ref_id', 0)) == chunk_id:
                    chunk_data = chunk
                    break

            if chunk_data:
                # citation_map would provide: author, year, title
                # For now, structure matches what auditor expects
                citations.append({
                    'chunk_id': chunk_id,
                    'source': chunk_data.get('filename', 'unknown'),
                    'content_preview': chunk_data.get('content', '')[:150]
                })

        return citations

    def _detect_gaps(self, prose: str) -> list[str]:
        """Detect over-constrained phrases that indicate information gaps."""
        gap_patterns = [
            "I don't have",
            "I cannot find",
            "not in the retrieved",
            "no information about",
            "unable to find",
            "doesn't appear",
            "not available in",
            "insufficient information"
        ]

        detected = []
        for pattern in gap_patterns:
            if pattern.lower() in prose.lower():
                detected.append(pattern)

        return detected


async def quick_write(
    llm_func: callable,
    topic: str,
    chunks: list[dict],
    citation_map_path: str = "citation_map.json"
) -> str:
    """
    Quick one-shot writing (no auditor loop).

    Use for short tasks where you don't need verification.
    For dissertation chapters, use WriteAgent with auditor loop.

    Args:
        llm_func: LLM function
        topic: What to write about
        chunks: Retrieved chunks
        citation_map_path: Path to citation_map.json for MLA formatting

    Returns:
        Generated prose (unverified)
    """
    agent = WriteAgent(llm_func)

    context = ""
    for i, chunk in enumerate(chunks):
        chunk_id = chunk.get('ref_id', str(i + 1))
        content = chunk.get('content', '')[:800]
        context += f"\n[CHUNK-{chunk_id}]\n{content}\n"

    prompt = f"""Write a paragraph about: {topic}

Use only the retrieved chunks below. Cite with [CHUNK-N] markers.
MLA format: (Author Year)

{context}

Write now:"""

    system_prompt = """You are academic writing assistant.
Every claim must cite [CHUNK-N].
Use MLA 9th: (Author Year).
If claim unsupported, say "I don't have information." """

    return await llm_func(prompt, system_prompt=system_prompt)