# language: Python 3.11, file: captcha_solver.py
"""
Capsolver API — ImageToTextTask.
Docs: https://docs.capsolver.com/guide/recognition/ImageToTextTask.html
"""
import aiohttp, base64, asyncio
from config import CAPSOLVER_KEY

API = "https://api.capsolver.com"

async def solve_image_captcha(image_path: str, timeout: int = 60) -> str:
    if not CAPSOLVER_KEY:
        raise RuntimeError("CAPSOLVER_KEY not set")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    async with aiohttp.ClientSession() as s:
        payload = {
            "clientKey": CAPSOLVER_KEY,
            "task": {"type": "ImageToTextTask", "body": b64, "module": "common"},
        }
        async with s.post(f"{API}/createTask", json=payload) as r:
            j = await r.json()
        if j.get("errorId"):
            raise RuntimeError(f"capsolver createTask: {j.get('errorDescription')}")
        task_id = j["taskId"]

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(1.5)
            async with s.post(f"{API}/getTaskResult",
                              json={"clientKey": CAPSOLVER_KEY, "taskId": task_id}) as r:
                j = await r.json()
            if j.get("errorId"):
                raise RuntimeError(f"capsolver result: {j.get('errorDescription')}")
            if j.get("status") == "ready":
                sol = j["solution"].get("text", "").strip()
                if not sol:
                    raise RuntimeError("capsolver: empty solution")
                return sol
        raise RuntimeError("capsolver: timeout")
