.PHONY: verify start test e2e inspector down clean

verify: start test e2e inspector

start:
	docker compose up -d --build --wait

test:
	uv sync --dev --locked
	uv run pytest

e2e:
	uv run ch24-verify --url http://127.0.0.1:8024 --n8n-url http://127.0.0.1:5678 --jaeger-url http://127.0.0.1:16686 --output reports/verification.json

inspector:
	npx -y @modelcontextprotocol/inspector@2.8.0 --cli http://127.0.0.1:8025/mcp --transport http --protocol-era legacy --header "Authorization: Bearer chapter-24-local-mcp-token-change-me" --method tools/list --strict --format json > reports/inspector-tools.json
	npx -y @modelcontextprotocol/inspector@2.8.0 --cli http://127.0.0.1:8025/mcp --transport http --protocol-era legacy --header "Authorization: Bearer chapter-24-local-mcp-token-change-me" --method tools/call --tool-name search_documents --tool-args-json '{"query":"Compliance","limit":3}' --format json > reports/inspector-search.json
	npx -y @modelcontextprotocol/inspector@2.8.0 --cli http://127.0.0.1:8025/mcp --transport http --protocol-era modern --header "Authorization: Bearer chapter-24-local-mcp-token-change-me" --method tools/list --strict --format json > reports/inspector-tools-modern.json

down:
	docker compose down

clean:
	docker compose down --volumes
