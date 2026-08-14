import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_check_rate_limit_uses_authenticated_user_bucket():
    """Different JWT users should not share the same user rate-limit bucket."""
    import app.gateway.rate_limit as rate_limit_module

    original_configs = {
        name: config.copy()
        for name, config in rate_limit_module.rate_limiter.configs.items()
    }
    rate_limit_module.rate_limiter._requests.clear()

    try:
        rate_limit_module.rate_limiter.configs["user"] = {
            "max_requests": 1,
            "window_seconds": 60,
        }
        rate_limit_module.rate_limiter.configs["tenant"] = {
            "max_requests": 10,
            "window_seconds": 60,
        }

        await rate_limit_module.check_rate_limit(
            request=None,
            user_info={"user_id": 1, "tenant_id": 7},
        )

        with pytest.raises(HTTPException) as exc_info:
            await rate_limit_module.check_rate_limit(
                request=None,
                user_info={"user_id": 1, "tenant_id": 7},
            )
        assert exc_info.value.status_code == 429

        await rate_limit_module.check_rate_limit(
            request=None,
            user_info={"user_id": 2, "tenant_id": 7},
        )
    finally:
        rate_limit_module.rate_limiter.configs = original_configs
        rate_limit_module.rate_limiter._requests.clear()
