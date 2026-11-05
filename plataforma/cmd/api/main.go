// API HTTP/JSON del sistema de consorcios.
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ncmartin77/consorcio/plataforma/internal/consorcios"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/auth"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/config"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/database"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/httpx"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/tenant"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	if err := correr(); err != nil {
		slog.Error("api", "error", err)
		os.Exit(1)
	}
}

func correr() error {
	cfg, err := config.Cargar()
	if err != nil {
		return err
	}
	ctx, cancelar := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancelar()

	pool, err := database.Conectar(ctx, cfg.DatabaseURL)
	if err != nil {
		return err
	}
	defer pool.Close()

	srv := &http.Server{
		Addr:              cfg.DireccionHTTP,
		Handler:           rutas(cfg, pool),
		ReadHeaderTimeout: 10 * time.Second,
	}
	go func() {
		<-ctx.Done()
		apagar, listo := context.WithTimeout(context.Background(), 15*time.Second)
		defer listo()
		_ = srv.Shutdown(apagar)
	}()

	slog.Info("api escuchando", "addr", cfg.DireccionHTTP, "entorno", cfg.Entorno)
	if err := srv.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
}

func rutas(cfg config.Config, pool *pgxpool.Pool) http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID, middleware.RealIP, middleware.Recoverer)

	r.Get("/healthz", func(w http.ResponseWriter, r *http.Request) {
		if err := pool.Ping(r.Context()); err != nil {
			httpx.Error(w, http.StatusServiceUnavailable, "base de datos no disponible")
			return
		}
		httpx.JSON(w, http.StatusOK, map[string]string{"estado": "ok", "entorno": cfg.Entorno})
	})

	r.Route("/api/v1", func(r chi.Router) {
		r.Use(auth.Requerir(cfg.Entorno))

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
		})
	})
	return r
}
