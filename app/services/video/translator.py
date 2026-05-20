import os
from typing import List
from app.core.config import get_settings


async def translate_sorani_to_arabic(sorani_text: str, max_chars: int | None = None) -> str:
    """
    Translate Kurdish Sorani text to Arabic using OpenAI or Anthropic API.
    Respects char count constraint to match original pacing.
    """
    settings = get_settings()
    
    if max_chars is None:
        max_chars = settings.STORE_CONTEXT_MAX_LENGTH
    
    system_prompt = (
        "You are a professional translator. Translate the following Kurdish Sorani text to Iraqi Arabic. "
        "Preserve the tone, politeness level, and length of the original text. "
        "Do not add explanations or extra commentary."
    )
    
    user_prompt = f"Translate: {sorani_text}"
    
    if settings.OPENAI_API_KEY:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_chars,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    
    if settings.ANTHROPIC_API_KEY:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_chars,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        return response.content[0].text.strip()
    
    raise RuntimeError("No AI API key available for translation")


async def translate_segments(segments: List[dict]) -> List[dict]:
    """
    Translate a list of segments from Sorani to Arabic.
    Preserves timestamps and appends translated text.

    Args:
        segments: [{"start": float, "end": float, "text": str}, ...]

    Returns:
        [{"start": float, "end": float, "text": str, "arabic": str}, ...]
    """
    results = []
    for seg in segments:
        arabic_text = await translate_sorani_to_arabic(seg["text"])
        seg["arabic"] = arabic_text
        results.append(seg)
    
    return results