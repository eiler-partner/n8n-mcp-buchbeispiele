"""Derselbe zustandslose MCP-Dienst über stdio oder Streamable HTTP."""

from __future__ import annotations

import argparse

from mcp.server import MCPServer


server = MCPServer("Transport Lab", version="1.0.0")


@server.tool()
def echo_ticket(ticket_id: str) -> dict[str, str]:
    """Liefere eine synthetische Ticket-ID ohne externe Nebenwirkung zurück."""
    if not ticket_id.startswith("LAB-"):
        raise ValueError("Nur synthetische LAB-Tickets sind erlaubt")
    return {"ticket_id": ticket_id, "status": "checked"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--port", type=int, default=18075)
    args = parser.parse_args()
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(
            transport="streamable-http",
            host="127.0.0.1",
            port=args.port,
            stateless_http=True,
            json_response=True,
        )


if __name__ == "__main__":
    main()
