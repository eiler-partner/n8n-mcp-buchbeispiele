import asyncio

from mcp_transport_lab.verify import verify


def test_two_real_transports_and_version_rejection() -> None:
    result = asyncio.run(verify())
    assert result["stdio"] == result["http"]
    assert result["wrong_version_http_status"] == 400
    assert result["wrong_version_rpc_code"] == -32022
