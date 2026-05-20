import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import init_db, get_database
from app.services.fish_speech_client import generate_voice_clone


REFERENCE_VOICES = [
    {"filename": "erbil_male.wav", "name": "Erbil Male", "language": "ckb"},
    {"filename": "baghdad_female.wav", "name": "Baghdad Female", "language": "arb"},
    {"filename": "sulaymaniye_female.wav", "name": "Sulaymaniye Female", "language": "ckb"},
    {"filename": "basra_male.wav", "name": "Basra Male", "language": "arb"},
    {"filename": " Duhok_female.wav", "name": "Duhok Female", "language": "ckb"},
]

REFERENCE_AUDIO_DIR = Path("reference_voices")
STATIC_VOICES_DIR = Path("static/voices")
GREETING_TEXT_AR = "مرحباً بك في خدمة الترجمة الموحدة"
GREETING_TEXT_CKB = "بەخێربێت بۆ خزمەتگوزاری وەرگێڕی یەکگرتوو"


async def create_voice_library_table():
    async with get_database() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS voice_library (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                language TEXT NOT NULL,
                audio_url TEXT NOT NULL
            )
        """)
        await db.commit()


async def seed_voice_library():
    await init_db()
    await create_voice_library_table()

    STATIC_VOICES_DIR.mkdir(parents=True, exist_ok=True)

    for voice in REFERENCE_VOICES:
        ref_path = REFERENCE_AUDIO_DIR / voice["filename"]
        if not ref_path.exists():
            print(f"[SKIP] Reference file not found: {ref_path}")
            continue

        greeting = GREETING_TEXT_AR if voice["language"] == "arb" else GREETING_TEXT_CKB
        output_filename = f"{voice['filename'].replace('.wav', '')}_greeting.wav"
        output_path = STATIC_VOICES_DIR / output_filename

        success, result = await generate_voice_clone(
            text=greeting,
            reference_audio_path=str(ref_path),
            output_path=str(output_path),
        )

        if success and result:
            audio_url = f"/static/voices/{output_filename}"
            async with get_database() as db:
                await db.execute(
                    "INSERT INTO voice_library (name, language, audio_url) VALUES (?, ?, ?)",
                    (voice["name"], voice["language"], audio_url),
                )
                await db.commit()
            print(f"[OK] Seeded: {voice['name']} -> {audio_url}")
        else:
            print(f"[FAIL] Failed: {voice['name']}")

    print("[DONE] Voice library seeding complete.")


if __name__ == "__main__":
    asyncio.run(seed_voice_library())