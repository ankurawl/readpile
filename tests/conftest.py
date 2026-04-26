import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow (>5s)")
    config.addinivalue_line("markers", "network: marks tests requiring network access")
    config.addinivalue_line("markers", "audio: marks tests requiring Whisper/audio deps")
