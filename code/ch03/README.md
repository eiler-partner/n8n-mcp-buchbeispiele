# Kapitel 3: HTTP-, JSON- und Containerlabor

Die Test-API verwendet nur erfundene Dokumente. Sie besitzt absichtlich keine
Authentifizierung und darf nur lokal verwendet werden.

## Start im Container

```sh
docker build -t buch-ch03 code/ch03
docker run --rm --name buch-ch03 -p 127.0.0.1:8080:8080 buch-ch03
```

Ohne Docker kann die API nach Installation von
`code/ch03/requirements.txt` mit
`python code/ch03/api.py` gestartet werden. Sie bindet dann
standardmaessig nur an `127.0.0.1:8080`. Im Container setzt das
Image `HOST=0.0.0.0`; der Docker-Startbefehl veroeffentlicht den
Port trotzdem nur an der Loopback-Adresse des Hosts.

In einem zweiten Terminal:

```sh
curl -i http://127.0.0.1:8080/health
curl -i http://127.0.0.1:8080/documents/doc-1
curl -i 'http://127.0.0.1:8080/documents?limit=1'
curl -i http://127.0.0.1:8080/reviews
curl -i http://127.0.0.1:8080/documents/doc-999
curl -i -X POST http://127.0.0.1:8080/reviews \
  -H 'Content-Type: application/json' -d '{"document_id":'
```

Die letzten drei Aufrufe sind absichtlich fehlerhaft: 405, 404 und 400.
Ein gueltiger Schreibaufruf:

```sh
curl -i -X POST http://127.0.0.1:8080/reviews \
  -H 'Content-Type: application/json' \
  -d '{"document_id":"doc-1","decision":"approve"}'
```

## Tests und Schema-Pruefung

```sh
uv run --no-project --with jsonschema==4.26.0 \
  python -m unittest discover -s code/ch03/tests -v
uv run --no-project --with jsonschema==4.26.0 \
  python code/ch03/validate_response.py \
  http://127.0.0.1:8080/documents/doc-1
docker inspect --format '{{.State.Health.Status}}' buch-ch03
docker logs buch-ch03
```

Alternativ kann Python in einer virtuellen Umgebung mit
`code/ch03/requirements.txt` installiert werden. Ein benanntes Volume fuer
Testdaten wird mit `--mount source=buch-ch03-data,target=/data` eingebunden.
Es ist fuer das Basislabor nicht erforderlich. Es entstehen keine echten
Freigaben oder Publikationen.
