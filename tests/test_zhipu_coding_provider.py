"""智谱 GLM Coding Plan 的显式 Provider 与错误提示回归测试。"""

from backend.modules.providers import create_provider
from backend.modules.providers.error_messages import (
    format_openai_error,
    friendly_openai_error,
)
from backend.modules.providers.registry import (
    ZHIPU_CODING_API_BASE,
    ZHIPU_STANDARD_API_BASE,
    get_provider_metadata,
    find_provider_by_api_base,
)
from backend.modules.providers.thinking_profiles import (
    apply_reasoning_request_fields,
)


ZHIPU_1113_ERROR = (
    'Error code: 429 - {"error":{"code":"1113",'
    '"message":"余额不足或无可用资源包,请充值。"}}'
)


def test_coding_plan_is_a_distinct_provider():
    standard = get_provider_metadata("zhipu")
    coding = get_provider_metadata("zhipu_coding")

    assert standard is not None
    assert coding is not None
    assert standard.default_api_base == ZHIPU_STANDARD_API_BASE
    assert coding.default_api_base == ZHIPU_CODING_API_BASE
    assert coding.default_model == "GLM-5"
    assert coding.name == "Zhipu AI (GLM Coding Plan)"


def test_factory_uses_the_coding_plan_endpoint():
    provider = create_provider(provider_id="zhipu_coding")

    assert provider.api_base == ZHIPU_CODING_API_BASE
    assert provider.default_model == "GLM-5"


def test_api_base_detection_distinguishes_standard_and_coding_plan():
    assert (
        find_provider_by_api_base(ZHIPU_STANDARD_API_BASE).id
        == "zhipu"
    )
    assert (
        find_provider_by_api_base(f"{ZHIPU_CODING_API_BASE}/").id
        == "zhipu_coding"
    )


def test_1113_on_standard_endpoint_suggests_coding_plan():
    message = friendly_openai_error(
        ZHIPU_1113_ERROR,
        provider_id="zhipu",
        api_base=ZHIPU_STANDARD_API_BASE,
    )

    assert "GLM Coding Plan" in message
    assert ZHIPU_CODING_API_BASE in message


def test_1113_on_coding_endpoint_does_not_suggest_switching_endpoint():
    message = friendly_openai_error(
        ZHIPU_1113_ERROR,
        provider_id="zhipu_coding",
        api_base=ZHIPU_CODING_API_BASE,
    )

    assert "账户余额不足" in message
    assert "将 Base URL 改为" not in message


def test_1113_on_unrelated_endpoint_keeps_generic_balance_message():
    message = friendly_openai_error(
        ZHIPU_1113_ERROR,
        provider_id="custom_openai",
        api_base="https://example.com/v1",
    )

    assert "账户余额不足" in message
    assert "GLM Coding Plan" not in message


def test_formatted_error_keeps_upstream_detail():
    message = format_openai_error(
        ZHIPU_1113_ERROR,
        provider_id="zhipu",
        api_base=ZHIPU_STANDARD_API_BASE,
    )

    assert "GLM Coding Plan" in message
    assert "1113" in message


def test_coding_plan_provider_uses_zhipu_thinking_switch():
    params = {}
    applied = apply_reasoning_request_fields(
        params,
        provider_id="zhipu_coding",
        model="GLM-5",
        api_base=ZHIPU_CODING_API_BASE,
        thinking_enabled=False,
    )

    assert applied == ("extra_body.thinking",)
    assert params["extra_body"]["thinking"] == {"type": "disabled"}