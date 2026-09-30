# Kapitel 20: OAuth, Consent und Mandantentrennung

Das Labor enthält einen geschützten, ausschließlich lesenden Python-MCP-Server.
Der Server prüft Signatur, Issuer, Audience und Scope, leitet den Mandanten nur
aus dem geprüften Token ab und schreibt minimierte Auditereignisse ohne Token
oder Dokumentinhalt.

## Automatisierte Pflichtprüfung

```bash
uv sync --frozen --dev
uv run pytest
```

Die Tests starten den Server an einem freien lokalen Port und prüfen unter
anderem:

- `401` ohne oder mit ungültigem Token,
- `403 insufficient_scope`,
- falsche Audience,
- verweigerten Consent,
- Zugriff von Mandant A auf eine Dokument-ID von Mandant B,
- vollständige Auditfelder ohne gespeicherten Bearer-Token.

## Docker-Labor mit kurzlebigem Fixture-Token

```bash
docker compose up -d --build --wait
uv run mcp-auth-token
```

Die Token-CLI gibt einen fünf Minuten gültigen Testtoken aus. Er kann im MCP
Inspector oder in einem HTTP-Client als `Authorization: Bearer …` verwendet
werden. Der symmetrische Schlüssel und alle Beispielpasswörter sind bewusst
nur lokale, nicht geheime Fixtures. Sie dürfen niemals für einen erreichbaren
Dienst wiederverwendet werden.

## Zusätzlicher Integrationsschritt mit Keycloak

```bash
docker compose --profile keycloak up -d --build --wait
```

Danach stehen bereit:

- Keycloak: `http://127.0.0.1:8081`
- MCP Resource Server mit Keycloak-JWTs: `http://127.0.0.1:8020/mcp`
- vorregistrierter öffentlicher Client: `mcp-book-client`
- Benutzer `alice` / Passwort `alice-local-only` für `tenant-a`
- Benutzer `bob` / Passwort `bob-local-only` für `tenant-b`

Der Client verwendet Authorization Code mit PKCE. Beim ersten Login zeigt
Keycloak eine Consent-Seite für `documents:read`. DCR ist hier absichtlich
nicht nötig: Vorregistrierung ist eine zulässige MCP-Registrierungsstrategie.

Für den separaten Browser-Test im MCP Inspector:

1. Streamable HTTP und `http://127.0.0.1:8020/mcp` wählen.
2. Den OAuth-Schnellablauf starten und als Client-ID `mcp-book-client`
   verwenden.
3. Den Scope `documents:read` anfordern und sich als `alice` oder `bob`
   anmelden.
4. Die Consent-Seite bestätigen und danach `list_documents` aufrufen.

Die Realm-Fixture erlaubt die lokale Inspector-Callback-URL
`http://localhost:6274/oauth/callback`. Meldet die verwendete
Inspector-Version eine andere Callback-URL, muss genau diese URL vor dem
erneuten Realm-Import in `keycloak/mcp-lab-realm.json` ergänzt werden.

Das Profil demonstriert einen realen OIDC-Issuer und asymmetrisch signierte
Tokens. Die automatisierten negativen Tests bleiben davon unabhängig und
laufen deshalb auch offline reproduzierbar.

## Aufräumen

```bash
docker compose --profile keycloak down --volumes
```
