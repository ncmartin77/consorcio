// Package personas: propietarios, inquilinos y contactos, y sus vínculos con las
// unidades a lo largo del tiempo (nunca se borran: se cierran con fecha "hasta").
package personas

import (
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shopspring/decimal"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/api"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/fecha"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/httpx"
)

type Servicio struct{ pool *pgxpool.Pool }

func NuevoServicio(pool *pgxpool.Pool) *Servicio { return &Servicio{pool: pool} }

type datos struct {
	Nombre    *string `json:"nombre"`
	Documento *string `json:"documento"`
	Email     *string `json:"email"`
	Telefono  *string `json:"telefono"`
	Notas     *string `json:"notas"`
}

type altaVinculo struct {
	PersonaID             uuid.UUID        `json:"persona_id"`
	TipoVinculo           string           `json:"tipo_vinculo"`
	PorcentajeTitularidad *decimal.Decimal `json:"porcentaje_titularidad"`
	RecibeLiquidacion     bool             `json:"recibe_liquidacion"`
	Desde                 fecha.Fecha      `json:"desde"`
}

type finVinculo struct {
	Hasta fecha.Fecha `json:"hasta"`
}

func vacio(p *string) bool { return p != nil && strings.TrimSpace(*p) == "" }

// Rutas cuelga de /api/v1/administraciones/{administracionID}.
func (s *Servicio) Rutas(r chi.Router) {
	r.Get("/personas", func(w http.ResponseWriter, r *http.Request) {
		var texto *string
		if q := strings.TrimSpace(r.URL.Query().Get("q")); q != "" {
			texto = &q
		}
		api.Leer(w, r, s.pool, "personas", func(tx api.Tx) ([]dbq.BuscarPersonasRow, error) {
			return api.Lista(tx.Q.BuscarPersonas(r.Context(), texto))
		})
	})

	r.Post("/personas", func(w http.ResponseWriter, r *http.Request) {
		var d datos
		if !httpx.Leer(w, r, &d) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusCreated, "persona", func(tx api.Tx) (dbq.Persona, error) {
			if d.Nombre == nil || vacio(d.Nombre) {
				return dbq.Persona{}, api.Invalido("falta el nombre")
			}
			p, err := tx.Q.CrearPersona(r.Context(), dbq.CrearPersonaParams{
				Nombre: strings.TrimSpace(*d.Nombre), Documento: d.Documento, Email: d.Email, Telefono: d.Telefono, Notas: d.Notas,
			})
			if err == nil {
				tx.Auditar("persona_creada", map[string]any{"persona_id": p.ID})
			}
			return p, err
		})
	})

	r.Get("/personas/{personaID}", func(w http.ResponseWriter, r *http.Request) {
		pid, ok := api.ID(w, r, "personaID", "persona")
		if !ok {
			return
		}
		api.Leer(w, r, s.pool, "persona", func(tx api.Tx) (dbq.Persona, error) {
			return tx.Q.ObtenerPersona(r.Context(), pid)
		})
	})

	r.Patch("/personas/{personaID}", func(w http.ResponseWriter, r *http.Request) {
		pid, ok := api.ID(w, r, "personaID", "persona")
		var d datos
		if !ok || !httpx.Leer(w, r, &d) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusOK, "persona", func(tx api.Tx) (dbq.Persona, error) {
			if vacio(d.Nombre) {
				return dbq.Persona{}, api.Invalido("el nombre no puede quedar vacío")
			}
			p, err := tx.Q.ActualizarPersona(r.Context(), dbq.ActualizarPersonaParams{
				ID: pid, Nombre: d.Nombre, Documento: d.Documento, Email: d.Email, Telefono: d.Telefono, Notas: d.Notas,
			})
			if err == nil {
				tx.Auditar("persona_modificada", map[string]any{"persona_id": pid})
			}
			return p, err
		})
	})

	r.Get("/personas/{personaID}/vinculos", func(w http.ResponseWriter, r *http.Request) {
		pid, ok := api.ID(w, r, "personaID", "persona")
		if !ok {
			return
		}
		api.Leer(w, r, s.pool, "persona", func(tx api.Tx) ([]dbq.VinculosDePersonaRow, error) {
			if _, err := tx.Q.ObtenerPersona(r.Context(), pid); err != nil {
				return nil, err
			}
			return api.Lista(tx.Q.VinculosDePersona(r.Context(), pid))
		})
	})

	// Vínculos de una unidad. ?fecha=AAAA-MM-DD: vigentes ese día (por defecto hoy).
	// ?historial=1: todos.
	r.Get("/unidades/{unidadID}/vinculos", func(w http.ResponseWriter, r *http.Request) {
		uid, ok := api.ID(w, r, "unidadID", "unidad")
		if !ok {
			return
		}
		var f *fecha.Fecha
		if r.URL.Query().Get("historial") != "1" {
			hoy := fecha.Hoy()
			f = &hoy
			if s := r.URL.Query().Get("fecha"); s != "" {
				p, err := fecha.Parse(s)
				if err != nil {
					httpx.Error(w, http.StatusBadRequest, err.Error())
					return
				}
				f = &p
			}
		}
		api.Leer(w, r, s.pool, "unidad", func(tx api.Tx) ([]dbq.VinculosDeUnidadRow, error) {
			if _, err := tx.Q.ObtenerUnidad(r.Context(), uid); err != nil {
				return nil, err
			}
			return api.Lista(tx.Q.VinculosDeUnidad(r.Context(), dbq.VinculosDeUnidadParams{UnidadID: uid, Fecha: f}))
		})
	})

	r.Post("/unidades/{unidadID}/vinculos", func(w http.ResponseWriter, r *http.Request) {
		uid, ok := api.ID(w, r, "unidadID", "unidad")
		var a altaVinculo
		if !ok || !httpx.Leer(w, r, &a) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusCreated, "vínculo", func(tx api.Tx) (dbq.UnidadPersona, error) {
			switch {
			case a.PersonaID == uuid.Nil:
				return dbq.UnidadPersona{}, api.Invalido("falta persona_id")
			case a.Desde.EsCero():
				return dbq.UnidadPersona{}, api.Invalido("falta la fecha desde")
			case a.TipoVinculo != "propietario" && a.TipoVinculo != "inquilino" && a.TipoVinculo != "contacto":
				return dbq.UnidadPersona{}, api.Invalido("tipo_vinculo: propietario, inquilino o contacto")
			case a.PorcentajeTitularidad != nil && a.TipoVinculo != "propietario":
				return dbq.UnidadPersona{}, api.Invalido("el porcentaje de titularidad es solo para propietarios")
			}
			v, err := tx.Q.CrearVinculo(r.Context(), dbq.CrearVinculoParams{
				UnidadID: uid, PersonaID: a.PersonaID, TipoVinculo: a.TipoVinculo,
				PorcentajeTitularidad: a.PorcentajeTitularidad, RecibeLiquidacion: a.RecibeLiquidacion, Desde: a.Desde,
			})
			if err == nil {
				tx.Auditar("vinculo_creado", map[string]any{"vinculo_id": v.ID, "unidad_id": uid,
					"persona_id": a.PersonaID, "tipo": a.TipoVinculo, "desde": a.Desde})
			}
			return v, err
		})
	})

	r.Post("/vinculos/{vinculoID}/finalizar", func(w http.ResponseWriter, r *http.Request) {
		vid, ok := api.ID(w, r, "vinculoID", "vínculo")
		var f finVinculo
		if !ok || !httpx.Leer(w, r, &f) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusOK, "vínculo vigente", func(tx api.Tx) (dbq.UnidadPersona, error) {
			if f.Hasta.EsCero() {
				return dbq.UnidadPersona{}, api.Invalido("falta la fecha hasta")
			}
			v, err := tx.Q.FinalizarVinculo(r.Context(), dbq.FinalizarVinculoParams{ID: vid, Hasta: &f.Hasta})
			if err == nil {
				tx.Auditar("vinculo_finalizado", map[string]any{"vinculo_id": vid, "hasta": f.Hasta})
			}
			return v, err
		})
	})
}
