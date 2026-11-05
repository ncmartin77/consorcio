# No hace falta Go instalado: todo corre en contenedores.
COMPOSE := docker compose -f deploy/compose.yaml
GO      := docker run --rm -u $$(id -u):$$(id -g) -e HOME=/tmp -e GOPATH=/tmp/go -e GOMODCACHE=/go/pkg/mod -e GOCACHE=/tmp/.cache/go-build \
             -v $(CURDIR):/src -v consorcios-gomod:/go/pkg/mod -w /src --network host golang:1.27-alpine go
SQLC    := docker run --rm -u $$(id -u):$$(id -g) -v $(CURDIR):/src -w /src sqlc/sqlc:1.30.0

DB_OWNER := postgres://consorcios_owner:owner-local@127.0.0.1:55433/consorcios
DB_APP   := postgres://consorcios_app:app-local@127.0.0.1:55433/consorcios

.PHONY: up down reset logs sqlc build vet test web

up:            ## levanta db, s3, migraciones, api y worker
	$(COMPOSE) up -d --build --wait db api worker

down:
	$(COMPOSE) down

reset:         ## borra los datos locales de la plataforma
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f api worker

sqlc:          ## regenera internal/platform/dbq desde db/queries
	$(SQLC) generate

build:
	$(GO) build ./...

vet:
	$(GO) vet ./...

test:          ## pruebas, incluidas las de aislamiento RLS (requiere make up)
	docker run --rm -u $$(id -u):$$(id -g) -e HOME=/tmp -e GOPATH=/tmp/go -e GOMODCACHE=/go/pkg/mod -e GOCACHE=/tmp/.cache/go-build \
	  -e DATABASE_URL_OWNER=$(DB_OWNER) -e DATABASE_URL=$(DB_APP) \
	  -v $(CURDIR):/src -v consorcios-gomod:/go/pkg/mod -w /src --network host golang:1.27-alpine \
	  go test -count=1 ./...

web:           ## frontend en modo desarrollo
	cd web && npm install && npm run dev
