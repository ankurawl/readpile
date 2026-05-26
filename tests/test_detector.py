from readpile.core.detector import is_error_content

def test_detects_too_many_requests():
    text = "Error 429: Too Many Requests. Please slow down."
    assert is_error_content(text) is True

def test_detects_cloudflare_block():
    text = "Checking your browser before accessing site.com. Cloudflare DDoS protection."
    assert is_error_content(text) is True

def test_detects_short_garbage():
    text = "403 Forbidden"
    assert is_error_content(text) is True

def test_allows_valid_content():
    text = "This is a real article about AI. It has multiple paragraphs and useful info."
    assert is_error_content(text) is False
