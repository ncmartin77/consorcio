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

	"github.com/ncmartin77/consorcio/plataforma/internal/app"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/config"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/database"
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
		Handler:           app.Rutas(cfg, pool),
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
