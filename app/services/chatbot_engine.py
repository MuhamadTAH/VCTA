import json
import asyncio
from typing import AsyncGenerator
from app.core.config import get_settings


MAX_HISTORY_MESSAGES = 15


def build_system_prompt(store_id: int, context_rules: str, catalog_json: str) -> str:
    try:
        rules = json.loads(context_rules) if context_rules else {}
    except (json.JSONDecodeError, TypeError):
        rules = {}

    try:
        catalog = json.loads(catalog_json) if catalog_json else []
    except (json.JSONDecodeError, TypeError):
        catalog = []

    catalog_section = ""
    if catalog:
        catalog_section = "\n\n## Store Catalog:\n"
        for item in catalog:
            name = item.get("name", item.get("title", ""))
            price = item.get("price", "")
            desc = item.get("description", item.get("desc", ""))
            catalog_section += f"- {name} | {price} | {desc}\n"

    rules_section = ""
    if rules:
        rules_section = "\n\n## Store Context Rules:\n"
        for key, value in rules.items():
            rules_section += f"- {key}: {value}\n"

    return (
        "You are a helpful, friendly store assistant for this business. "
        "You respond in Kurdish Sorani or Arabic based on the user's language. "
        "Be concise, polite, and helpful. Do not invent information not provided in the catalog."
        f"{catalog_section}"
        f"{rules_section}"
        "\n\n## Important:\n"
        "- Only discuss products that exist in the catalog above\n"
        "- If you don't know something, say so honestly\n"
        "- Keep responses short and helpful (2-4 sentences max)\n"
        "- Be polite and use appropriate greetings in Kurdish or Arabic\n"
    )


async def generate_streaming_response(
    messages: list[dict],
    store_id: int,
    context_rules: str,
    catalog_json: str,
) -> AsyncGenerator[str, None]:
    settings = get_settings()
    system_prompt = build_system_prompt(store_id, context_rules, catalog_json)

    if settings.MINIMAX_API_KEY:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.MINIMAX_API_KEY,
            base_url=settings.MINIMAX_API_BASE_URL,
        )

        stream = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "system", "content": system_prompt}] + messages,
            stream=True,
            max_tokens=500,
            temperature=0.7,
        )

        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content

    elif settings.OPENAI_API_KEY:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        stream = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}] + messages,
            stream=True,
            stream_options={"include_usage": True},
            max_tokens=500,
            temperature=0.7,
        )

        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content

    elif settings.ANTHROPIC_API_KEY:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        stream = await client.messages.stream(
            model="claude-sonnet-4-20250514",
            system=system_prompt,
            messages=messages,
            max_tokens=500,
        )

        async with stream as stream_response:
            async for text_event in stream_response.text_events:
                if text_event.type == "content_block_delta":
                    yield text_event.delta.text

    else:
        yield "No AI provider configured. Please set MINIMAX_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY."


async def load_session_chat_history(session_id: str) -> list[dict]:
    from app.core.database import get_database

    async with get_database() as db:
        cursor = await db.execute(
            "SELECT chat_history_json FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if row and row[0]:
            try:
                history = json.loads(row[0])
                return history[-MAX_HISTORY_MESSAGES:]
            except (json.JSONDecodeError, TypeError):
                return []
        return []


async def save_session_chat_history(session_id: str, history: list[dict]) -> None:
    from app.core.database import get_database

    truncated = history[-MAX_HISTORY_MESSAGES:]
    async with get_database() as db:
        await db.execute(
            "UPDATE sessions SET chat_history_json = ? WHERE id = ?",
            (json.dumps(truncated), session_id),
        )
        await db.commit()


async def resilient_save_history(
    session_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    import logging
    try:
        async with get_database() as db:
            cursor = await db.execute(
                "SELECT chat_history_json FROM sessions WHERE id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            if row and row[0]:
                try:
                    history = json.loads(row[0])
                except (json.JSONDecodeError, TypeError):
                    history = []
            else:
                history = []

            history.append({"role": "user", "content": user_message})
            history.append({"role": "assistant", "content": assistant_message})

            truncated = history[-MAX_HISTORY_MESSAGES:]
            await db.execute(
                "UPDATE sessions SET chat_history_json = ? WHERE id = ?",
                (json.dumps(truncated), session_id),
            )
            await db.commit()
    except Exception as e:
        logging.warning(f"[resilient_save_history] failed for session {session_id}: {e}")


async def append_and_save_history(
    session_id: str,
    user_message: str,
    assistant_message: str,
) -> list[dict]:
    history = await load_session_chat_history(session_id)

    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": assistant_message})

    await save_session_chat_history(session_id, history)

    return history


async def get_store_context(store_id: int) -> tuple[str, str]:
    from app.core.database import get_database

    async with get_database() as db:
        cursor = await db.execute(
            "SELECT context_rules, catalog_json FROM stores WHERE id = ?",
            (store_id,),
        )
        row = await cursor.fetchone()
        if row:
            return (row[0] or "{}", row[1] or "[]")
        return "{}", "[]"
