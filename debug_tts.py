import sys, os
sys.path.insert(0, '.')
os.environ['MINIMAX_API_KEY'] = 'sk-cp-06MFM57O20X4GiT1ijm-X5TNn7qo53GhaliQemH3gkmUNe7b8w4vzi3HpT2NWC8XFIwTxerlkYCTSZdlbrtxlzHkZaMzhDRdfRO3UncPPE9HpZ0d0ezh36Y'

import asyncio, httpx, json

async def test():
    key = 'sk-cp-06MFM57O20X4GiT1ijm-X5TNn7qo53GhaliQemH3gkmUNe7b8w4vzi3HpT2NWC8XFIwTxerlkYCTSZdlbrtxlzHkZaMzhDRdfRO3UncPPE9HpZ0d0ezh36Y'
    base_url = 'https://api.minimax.io/v1'
    headers = {
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json'
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            'model': 'speech-2.8-hd',
            'text': 'Hello world, this is a test of the MiniMax TTS API.',
            'voice_setting': {'voice_id': 'female-tianmei'}
        }

        r = await client.post(base_url + '/t2a_v2', headers=headers, json=payload)
        status = r.status_code

        if status == 200:
            try:
                data = json.loads(r.content)
                code = data.get('base_resp', {}).get('status_code', 0)
                if code == 0:
                    audio_data = data.get('data', {}).get('audio', {})
                    print('Audio info:', audio_data)
                else:
                    print('Error:', data.get('base_resp', {}).get('status_msg', ''))
            except json.JSONDecodeError:
                with open('test_output.mp3', 'wb') as f:
                    f.write(r.content)
                print(f'Saved {len(r.content)} bytes to test_output.mp3')
        else:
            print(f'HTTP {status}')

asyncio.run(test())