"""
GLiNER Entity Extractor
=======================
Drop-in replacement for LLM entity extraction in LightRAG.
Uses GLiNER for fast, local entity extraction.
"""

import time
from typing import Optional

# Global model cache
_model = None
_model_load_time = 0


def load_model(model_name: str = "urchade/gliner_small-v2.1"):
    """Load GLiNER model (cached after first call)."""
    global _model, _model_load_time
    if _model is None:
        from gliner import GLiNER
        t0 = time.time()
        _model = GLiNER.from_pretrained(model_name)
        _model_load_time = time.time() - t0
        print(f"GLiNER loaded in {_model_load_time:.1f}s")
    return _model


def extract_entities_gliner(
    text: str,
    entity_types: list[str] = None,
    threshold: float = 0.3
) -> str:
    """
    Extract entities from text using GLiNER.
    
    Returns format compatible with LightRAG's entity extraction:
    (entity_name, entity_type, entity_description)
    """
    model = load_model()
    
    if entity_types is None:
        entity_types = ["Person", "Organization", "Location", "Event", "Date", "Book", "Concept"]
    
    t0 = time.time()
    entities = model.predict_entities(text, entity_types, threshold=threshold)
    extract_time = time.time() - t0
    
    # Convert to LightRAG format: ["entity", name, type, description]
    results = []
    for ent in entities:
        entity_name = ent["text"]
        entity_type = ent["label"]
        entity_description = f"{entity_name} ({entity_type})"
        results.append(f"entity, {entity_name}, {entity_type}, {entity_description}")
    
    return "\n".join(results)


def create_gliner_llm_func(original_llm_func: callable) -> callable:
    """
    Create an LLM function wrapper that uses GLiNER for entity extraction.
    
    For entity extraction prompts, uses GLiNER.
    For other prompts, uses the original LLM function.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    async def wrapper(
        prompt: str,
        system_prompt: Optional[str] = None,
        history_messages: list = [],
        **kwargs
    ) -> str:
        logger.info(f"[GLiNER] Called with system_prompt={system_prompt[:50] if system_prompt else None}...")
        
        # Check if this is an entity extraction prompt (starts with ---Role--- and contains entity instructions)
        if system_prompt and "---Role---" in system_prompt and "entity" in system_prompt.lower():
            logger.info("[GLiNER] Entity extraction detected, using GLiNER")
            # Extract text from prompt (LightRAG passes input_text in the prompt)
            text = prompt[-2000:] if len(prompt) > 2000 else prompt
            logger.info(f"[GLiNER] Input text length: {len(text)}")
            
            result = extract_entities_gliner(text)
            logger.info(f"[GLiNER] Result length: {len(result)}")
            logger.info(f"[GLiNER] Result preview: {result[:200]}")
            
            # CRITICAL: LightRAG requires <|COMPLETE|> delimiter at end
            result = result + "\n<|COMPLETE|>"
            
            return result
        else:
            logger.info(f"[GLiNER] Non-entity prompt, using original LLM")
            # Use original LLM for non-entity-extraction tasks
            return await original_llm_func(
                prompt, 
                system_prompt=system_prompt, 
                history_messages=history_messages, 
                **kwargs
            )
    
    return wrapper
