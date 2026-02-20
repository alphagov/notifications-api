def test_security_headers_set(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["X-Permitted-Cross-Domain-Policies"] == "none"
    assert response.headers["Cache-Control"] == "no-store, no-cache, private, must-revalidate"
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains; preload"
