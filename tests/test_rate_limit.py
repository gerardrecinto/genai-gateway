from genai_gateway.rate_limit.token_bucket import TokenBucketLimiter


def test_allows_up_to_capacity():
    limiter = TokenBucketLimiter(capacity=3, refill_per_second=0)
    assert limiter.allow("client-a")
    assert limiter.allow("client-a")
    assert limiter.allow("client-a")
    assert not limiter.allow("client-a")


def test_buckets_are_independent_per_client():
    limiter = TokenBucketLimiter(capacity=1, refill_per_second=0)
    assert limiter.allow("client-a")
    assert not limiter.allow("client-a")
    assert limiter.allow("client-b")


def test_refill_allows_more_requests_over_time():
    import time

    limiter = TokenBucketLimiter(capacity=1, refill_per_second=100)
    assert limiter.allow("client-a")
    assert not limiter.allow("client-a")
    time.sleep(0.02)  # ~2 tokens worth at 100/sec
    assert limiter.allow("client-a")
