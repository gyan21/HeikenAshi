import asyncio
import threading

_loop = asyncio.new_event_loop()


def _run_loop(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


def start_background_loop():
    """Start the global asyncio event loop in a background thread."""
    thread = threading.Thread(target=_run_loop, args=(_loop,), daemon=True)
    thread.start()


def get_loop() -> asyncio.AbstractEventLoop:
    """Return the global asyncio event loop instance."""
    return _loop
