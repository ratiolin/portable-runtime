from portable_runtime.interfaces.transport import (
    IdempotencyStore,
    TransportErrorCategory,
    classify_transport_error,
    compute_webhook_signature,
    verify_webhook_signature,
)


def test_classify_timeout():
    assert classify_transport_error(exception=TimeoutError("timeout")) == TransportErrorCategory.TIMEOUT
    assert classify_transport_error(408) == TransportErrorCategory.TIMEOUT
    assert classify_transport_error(429) == TransportErrorCategory.RATE_LIMITED
    assert classify_transport_error(401) == TransportErrorCategory.AUTH
    assert classify_transport_error(500) == TransportErrorCategory.TRANSIENT
    assert classify_transport_error(400) == TransportErrorCategory.PERMANENT
    assert classify_transport_error(200) == TransportErrorCategory.UNKNOWN
    assert classify_transport_error(None, exception=RuntimeError("auth failed")) == TransportErrorCategory.AUTH

def test_webhook_signature():
    payload = b'{"a":1}'
    secret = "s3cret"
    sig = compute_webhook_signature(payload, secret)
    assert verify_webhook_signature(payload, sig, secret)
    assert not verify_webhook_signature(payload, "sha256=bad", secret)
    assert not verify_webhook_signature(payload, sig, "")
    # sha1 variant
    sig1 = compute_webhook_signature(payload, secret, algorithm="sha1")
    assert sig1.startswith("sha1=")
    assert verify_webhook_signature(payload, sig1, secret, algorithm="sha1")

def test_idempotency_store():
    store = IdempotencyStore(ttl_seconds=1, max_entries=2)
    assert store.check_and_store("k1") is True
    assert store.check_and_store("k1") is False
    assert store.contains("k1")
    assert len(store) == 1
    store.check_and_store("k2")
    store.check_and_store("k3")  # evict oldest due to max_entries=2
    assert len(store) == 2
    store.clear()
    assert len(store) == 0
