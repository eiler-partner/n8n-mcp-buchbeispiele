from policy_mcp.domain import sha256_text


def test_sha256_text_is_stable() -> None:
    result = sha256_text("MCP")
    assert result.algorithm == "sha256"
    assert result.byte_length == 3
    assert result.digest == "53f13ae99ed53bd346eb8e1c8cefb7ef8260683b50401caf101360967ea052aa"
