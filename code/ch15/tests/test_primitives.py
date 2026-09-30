from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator, ValidationError
from mcp import Client
from mcp.types import ElicitResult, PromptReference, ResourceTemplateReference

from mcp_primitives_lab.server import POLICIES, server
from mcp_primitives_lab.url_mode import DEMO_URL, input_required_url, resume_url


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_primitive_catalog_and_contract() -> None:
    async with Client(server, mode="2026-07-28") as client:
        tools = await client.list_tools()
        templates = await client.list_resource_templates()
        prompts = await client.list_prompts()
    assert [tool.name for tool in tools.tools] == ["check_policy"]
    tool = tools.tools[0]
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.destructive_hint is False
    assert set(tool.input_schema["properties"]) == {"policy_id"}
    assert tool.output_schema is not None
    Draft202012Validator.check_schema(tool.input_schema)
    Draft202012Validator.check_schema(tool.output_schema)
    assert [item.uri_template for item in templates.resource_templates] == ["policy://{policy_id}"]
    assert [prompt.name for prompt in prompts.prompts] == ["review_policy"]


@pytest.mark.anyio
async def test_resource_and_prompt_have_different_roles() -> None:
    async with Client(server, mode="2026-07-28") as client:
        resource = await client.read_resource("policy://POL-101")
        prompt = await client.get_prompt("review_policy", {"policy_id": "POL-101"})
    assert POLICIES["POL-101"]["text"] in resource.contents[0].text
    assert resource.contents[0].mime_type == "text/markdown"
    assert "policy://POL-101" in prompt.messages[0].content.text
    assert "Reisebelege" not in prompt.messages[0].content.text


@pytest.mark.anyio
async def test_unknown_resource_is_rejected() -> None:
    async with Client(server, mode="2026-07-28") as client:
        with pytest.raises(Exception, match="POL-999|not found|Not found"):
            await client.read_resource("policy://POL-999")


@pytest.mark.anyio
async def test_completion_only_suggests_allowed_ids() -> None:
    async with Client(server, mode="2026-07-28") as client:
        prompt = await client.complete(PromptReference(name="review_policy"), {"name": "policy_id", "value": "POL-10"})
        resource = await client.complete(
            ResourceTemplateReference(uri="policy://{policy_id}"),
            {"name": "policy_id", "value": "POL-102"},
        )
    assert prompt.completion.values == ["POL-101", "POL-102"]
    assert resource.completion.values == ["POL-102"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("action", "expected_status", "expected_period"),
    [
        ("accept", "checked", "2026-Q3"),
        ("decline", "declined", None),
        ("cancel", "cancelled", None),
    ],
)
async def test_form_elicitation_mrtr(action: str, expected_status: str, expected_period: str | None) -> None:
    seen = []

    async def answer(context, params):
        del context
        seen.append(params)
        content = {"period": "2026-Q3"} if action == "accept" else None
        return ElicitResult(action=action, content=content)

    async with Client(server, mode="2026-07-28", elicitation_callback=answer) as client:
        result = await client.call_tool("check_policy", {"policy_id": "POL-101"})
        tools = await client.list_tools()
    assert len(seen) == 1
    assert seen[0].mode == "form"
    assert result.is_error is False
    assert result.structured_content["status"] == expected_status
    assert result.structured_content["period"] == expected_period
    assert "period" not in tools.tools[0].input_schema["properties"]
    Draft202012Validator(tools.tools[0].output_schema).validate(result.structured_content)


@pytest.mark.anyio
async def test_invalid_tool_argument_does_not_become_success() -> None:
    async with Client(server, mode="2026-07-28") as client:
        result = await client.call_tool("check_policy", {"policy_id": "POL-999"})
    assert result.is_error is True


@pytest.mark.anyio
async def test_missing_elicitation_capability_is_rejected() -> None:
    async with Client(server, mode="2026-07-28") as client:
        with pytest.raises(Exception, match="capability|Capability|elicitation"):
            await client.call_tool("check_policy", {"policy_id": "POL-101"})


@pytest.mark.anyio
async def test_wrong_structured_result_is_rejected_by_output_contract() -> None:
    async with Client(server, mode="2026-07-28") as client:
        tool = (await client.list_tools()).tools[0]
    validator = Draft202012Validator(tool.output_schema)
    with pytest.raises(ValidationError):
        validator.validate({"policy_id": "POL-101", "status": "published"})


@pytest.mark.parametrize("action", ["accept", "decline", "cancel"])
def test_url_mode_simulation_is_out_of_band(action: str) -> None:
    first = input_required_url()
    request = first["result"]["inputRequests"]["external_step"]
    assert request["params"]["url"] == DEMO_URL
    assert request["params"]["mode"] == "url"
    retry = resume_url(first, action)
    assert retry["id"] != first["id"]
    assert retry["params"]["requestState"] == first["result"]["requestState"]
    assert retry["params"]["inputResponses"] == {"external_step": {"action": action}}
    assert "content" not in retry["params"]["inputResponses"]["external_step"]


def test_url_mode_rejects_foreign_domain_and_reused_id() -> None:
    first = input_required_url()
    with pytest.raises(ValueError, match="neue JSON-RPC-ID"):
        resume_url(first, "accept", request_id="call-1")
    first["result"]["inputRequests"]["external_step"]["params"]["url"] = "https://evil.invalid/"
    with pytest.raises(ValueError, match="Demo-Domain"):
        resume_url(first, "accept")
