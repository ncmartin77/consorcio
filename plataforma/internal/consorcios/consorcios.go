// Package consorcios: alta y consulta de consorcios de una administración.
package consorcios

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/database"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/httpx"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/tenant"
)

type Servicio struct{ pool *pgxpool.Pool }

func NuevoServicio(pool *pgxpool.Pool) *Servicio { return &Servicio{pool: pool} }

type Alta struct {
	Nombre    string  `json:"nombre"`
	Direccion *string `json:"direccion"`
	Cuit      *string `json:"cuit"`
}

func (s *Servicio) Listar(ctx context.Context, t tenant.Contexto) (lista []dbq.Consorcio, err error) {
	err = database.EnTenant(ctx, s.pool, t.AdministracionID, func(tx pgx.Tx) error {
		lista, err = dbq.New(tx).ListarConsorcios(ctx)
		return err
	})
	return lista, err
}

func (s *Servicio) Crear(ctx context.Context, t tenant.Contexto, a Alta) (c dbq.Consorcio, err error) {
	err = database.EnTenant(ctx, s.pool, t.AdministracionID, func(tx pgx.Tx) error {
		c, err = dbq.New(tx).CrearConsorcio(ctx, dbq.CrearConsorcioParams{
			Nombre: a.Nombre, Direccion: a.Direccion, Cuit: a.Cuit,
		})
		return err
	})
	return c, err
}

// Rutas cuelga de /api/v1/administraciones/{administracionID}.
func (s *Servicio) Rutas(r chi.Router) {
	r.Get("/consorcios", func(w http.ResponseWriter, r *http.Request) {
		lista, err := s.Listar(r.Context(), tenant.Desde(r.Context()))
		if err != nil {
			slog.Error("listar consorcios", "error", err)
			httpx.Error(w, http.StatusInternalServerError, "error interno")
			return
		}
		if lista == nil {
			lista = []dbq.Consorcio{}
		}
		httpx.JSON(w, http.StatusOK, lista)
	})
	r.Post("/consorcios", func(w http.ResponseWriter, r *http.Request) {
		t := tenant.Desde(r.Context())
		if t.Rol == "consulta" {
			httpx.Error(w, http.StatusForbidden, "sin permiso")
			return
		}
		var a Alta
		if err := json.NewDecoder(r.Body).Decode(&a); err != nil || strings.TrimSpace(a.Nombre) == "" {
			httpx.Error(w, http.StatusBadRequest, "falta el nombre")
			return
		}
		c, err := s.Crear(r.Context(), t, a)
		if err != nil {
			slog.Error("crear consorcio", "error", err)
			httpx.Error(w, http.StatusInternalServerError, "error interno")
			return
		}
		httpx.JSON(w, http.StatusCreated, c)
	})
}
