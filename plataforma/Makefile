# No hace falta Go instalado: todo corre en contenedores.
COMPOSE := docker compose -f deploy/compose.yaml
GO      := docker run --rm -u $$(id -u):$$(id -g) -e HOME=/tmp -e GOPATH=/tmp/go -e GOMODCACHE=/go/pkg/mod -e GOCACHE=/tmp/.cache/go-build \
             -v $(CURDIR):/src -v consorcios-gomod:/go/pkg/mod -w /src --network host golang:1.27-alpine go
SQLC    := docker run --rm -u $$(id -u):$$(id -g) -v $(CURDIR):/src -w /src sqlc/sqlc:1.30.0

DB_OWNER := postgres://consorcios_owner:owner-local@127.0.0.1:55433/consorcios
DB_APP   := postgres://consorcios_app:app-local@127.0.0.1:55433/consorcios
S3_LOCAL := -e S3_ENDPOINT=http://127.0.0.1:59001 -e S3_BUCKET=plataforma -e S3_ACCESS_KEY_ID=local \
            -e S3_SECRET_ACCESS_KEY=local -e S3_CREAR_BUCKET=1
SUPABASE_ENV := deploy/.env.supabase

.PHONY: up up-supabase down reset logs sqlc build vet test test-supabase web

up:            ## levanta db, s3, migraciones, api y worker
	$(COMPOSE) up -d --build --wait db s3 api worker

up-supabase:   ## igual que up, pero los archivos van a Supabase Storage ($(SUPABASE_ENV))
	@test -f $(SUPABASE_ENV) || { echo "Falta $(SUPABASE_ENV): copiar deploy/.env.supabase.ejemplo y completar"; exit 1; }
	$(COMPOSE) --env-file $(SUPABASE_ENV) up -d --build --wait db s3 api worker

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
	  -e DATABASE_URL_OWNER=$(DB_OWNER) -e DATABASE_URL=$(DB_APP) $(S3_LOCAL) \
	  -v $(CURDIR):/src -v consorcios-gomod:/go/pkg/mod -w /src --network host golang:1.27-alpine \
	  go test -count=1 ./...

web:           ## frontend en modo desarrollo
	cd web && npm install && npm run dev

test-supabase: ## prueba de archivos contra Supabase Storage ($(SUPABASE_ENV))
	@test -f $(SUPABASE_ENV) || { echo "Falta $(SUPABASE_ENV): copiar deploy/.env.supabase.ejemplo y completar"; exit 1; }
	docker run --rm -u $$(id -u):$$(id -g) -e HOME=/tmp -e GOPATH=/tmp/go -e GOMODCACHE=/go/pkg/mod -e GOCACHE=/tmp/.cache/go-build \
	  --env-file $(SUPABASE_ENV) -v $(CURDIR):/src -v consorcios-gomod:/go/pkg/mod -w /src golang:1.27-alpine \
	  go test -count=1 -run TestArchivos -v ./tests/
