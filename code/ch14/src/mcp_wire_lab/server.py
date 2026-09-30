"""Der offizielle Python-SDK-Server; die Rohaufzeichnung macht der Client."""

from mcp.server import MCPServer


server = MCPServer("Kapitel-14-Wire-Labor", version="1.0.0")


@server.tool()
def read_policy(document_id: str) -> dict[str, str]:
    """Lies eine ausschließlich synthetische Richtlinie anhand ihrer ID."""
    if document_id != "DOC-101":
        raise ValueError("Unbekannte synthetische Dokument-ID")
    return {
        "document_id": "DOC-101",
        "title": "Reiserichtlinie",
        "status": "approved",
    }


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
