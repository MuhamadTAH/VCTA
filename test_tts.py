import asyncio
import sys
sys.path.insert(0, ".")

from app.services.video.synthesizer import synthesize_arabic_speech

async def test():
    output = "test_output.wav"
    text = "مرحباً بك في خدمة الترجمة الموحدة"

    print(f"Generating audio for: {text}")
    success = await synthesize_arabic_speech(text, output)
    if success:
        print(f"SUCCESS! Audio saved to {output}")
    else:
        print("FAILED - check your API key or ffmpeg")

asyncio.run(test())