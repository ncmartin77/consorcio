// Package unidades: unidades funcionales de un consorcio.
package unidades

import (
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/api"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/httpx"
)

type Servicio struct{ pool *pgxpool.Pool }

func NuevoServicio(pool *pgxpool.Pool) *Servicio { return &Servicio{pool: pool} }

type alta struct {
	Codigo      string  `json:"codigo"`
	Descripcion *string `json:"descripcion"`
	Piso        *string `json:"piso"`
	Tipo        string  `json:"tipo"`
}

type cambio struct {
	Codigo      *string `json:"codigo"`
	Descripcion *string `json:"descripcion"`
	Piso        *string `json:"piso"`
	Tipo        *string `json:"tipo"`
	Activa      *bool   `json:"activa"`
}

// Rutas cuelga de /api/v1/administraciones/{administracionID}.
func (s *Servicio) Rutas(r chi.Router) {
	r.Get("/consorcios/{consorcioID}", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		if !ok {
			return
		}
		api.Leer(w, r, s.pool, "consorcio", func(tx api.Tx) (dbq.Consorcio, error) {
			return tx.Q.ObtenerConsorcio(r.Context(), cid)
		})
	})

	r.Get("/consorcios/{consorcioID}/unidades", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		if !ok {
			return
		}
		api.Leer(w, r, s.pool, "consorcio", func(tx api.Tx) ([]dbq.Unidad, error) {
			if _, err := tx.Q.ObtenerConsorcio(r.Context(), cid); err != nil {
				return nil, err
			}
			return api.Lista(tx.Q.ListarUnidades(r.Context(), cid))
		})
	})

	r.Post("/consorcios/{consorcioID}/unidades", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		var a alta
		if !ok || !httpx.Leer(w, r, &a) {
			return
		}
		a.Codigo = strings.TrimSpace(a.Codigo)
		if a.Tipo == "" {
			a.Tipo = "departamento"
		}
		api.Escribir(w, r, s.pool, http.StatusCreated, "unidad", func(tx api.Tx) (dbq.Unidad, error) {
			if a.Codigo == "" {
				return dbq.Unidad{}, api.Invalido("falta el código de la unidad")
			}
			u, err := tx.Q.CrearUnidad(r.Context(), dbq.CrearUnidadParams{
				ConsorcioID: cid, Codigo: a.Codigo, Descripcion: a.Descripcion, Piso: a.Piso, Tipo: a.Tipo,
			})
			if err == nil {
				tx.Auditar("unidad_creada", map[string]any{"unidad_id": u.ID, "consorcio_id": cid, "codigo": u.Codigo})
			}
			return u, err
		})
	})

	r.Get("/unidades/{unidadID}", func(w http.ResponseWriter, r *http.Request) {
		uid, ok := api.ID(w, r, "unidadID", "unidad")
		if !ok {
			return
		}
		api.Leer(w, r, s.pool, "unidad", func(tx api.Tx) (dbq.Unidad, error) {
			return tx.Q.ObtenerUnidad(r.Context(), uid)
		})
	})

	r.Patch("/unidades/{unidadID}", func(w http.ResponseWriter, r *http.Request) {
		uid, ok := api.ID(w, r, "unidadID", "unidad")
		var c cambio
		if !ok || !httpx.Leer(w, r, &c) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusOK, "unidad", func(tx api.Tx) (dbq.Unidad, error) {
			if c.Codigo != nil && strings.TrimSpace(*c.Codigo) == "" {
				return dbq.Unidad{}, api.Invalido("el código no puede quedar vacío")
			}
			u, err := tx.Q.ActualizarUnidad(r.Context(), dbq.ActualizarUnidadParams{
				ID: uid, Codigo: c.Codigo, Descripcion: c.Descripcion, Piso: c.Piso, Tipo: c.Tipo, Activa: c.Activa,
			})
			if err == nil {
				tx.Auditar("unidad_modificada", map[string]any{"unidad_id": uid, "cambios": c})
			}
			return u, err
		})
	})
}
