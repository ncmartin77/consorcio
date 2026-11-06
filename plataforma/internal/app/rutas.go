// Package app arma el router HTTP de la API. Está fuera de cmd/api para que las
// pruebas puedan levantar la API completa con httptest.
package app

import (
	"log/slog"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ncmartin77/consorcio/plataforma/internal/consorcios"
	"github.com/ncmartin77/consorcio/plataforma/internal/personas"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/auth"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/config"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/httpx"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/tenant"
	"github.com/ncmartin77/consorcio/plataforma/internal/prorrateo"
	"github.com/ncmartin77/consorcio/plataforma/internal/unidades"
)

func Rutas(cfg config.Config, pool *pgxpool.Pool) http.Handler {
	r := chi.NewRouter()
	// Sin middleware.RealIP: confiaría en X-Forwarded-For de cualquiera. Detrás de
	// Nginx se agrega con la IP del proxy como única fuente confiable.
	r.Use(middleware.RequestID, middleware.Recoverer)

	r.Get("/healthz", func(w http.ResponseWriter, r *http.Request) {
		if err := pool.Ping(r.Context()); err != nil {
			httpx.Error(w, http.StatusServiceUnavailable, "base de datos no disponible")
			return
		}
		httpx.JSON(w, http.StatusOK, map[string]string{"estado": "ok", "entorno": cfg.Entorno})
	})

	ses := auth.NuevasSesiones(pool, cfg.Entorno)

	r.Route("/api/v1", func(r chi.Router) {
		r.Use(auth.ExigirCSRF)

		r.Post("/sesion", ses.Login)

		r.Group(func(r chi.Router) {
			r.Use(ses.Requerir)

			r.Delete("/sesion", ses.Logout)

			r.Get("/me", func(w http.ResponseWriter, r *http.Request) {
				u, _ := auth.UsuarioDe(r.Context())
				httpx.JSON(w, http.StatusOK, u)
			})

			r.Get("/me/administraciones", func(w http.ResponseWriter, r *http.Request) {
				uid, _ := auth.UsuarioID(r.Context())
				lista, err := dbq.New(pool).AdministracionesDeUsuario(r.Context(), uid)
				if err != nil {
					slog.Error("administraciones del usuario", "error", err)
					httpx.Error(w, http.StatusInternalServerError, "error interno")
					return
				}
				if lista == nil {
					lista = []dbq.AdministracionesDeUsuarioRow{}
				}
				httpx.JSON(w, http.StatusOK, lista)
			})

			r.Route("/administraciones/{administracionID}", func(r chi.Router) {
				r.Use(tenant.Requerir(pool))
				consorcios.NuevoServicio(pool).Rutas(r)
				unidades.NuevoServicio(pool).Rutas(r)
				personas.NuevoServicio(pool).Rutas(r)
				prorrateo.NuevoServicio(pool).Rutas(r)
			})
		})
	})
	return r
}
