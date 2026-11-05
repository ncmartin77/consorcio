// Worker de tareas asíncronas (PDF, tareas programadas, notificaciones).
//
// Esqueleto: por ahora solo verifica la conexión en cada ciclo. La cola persistida en
// PostgreSQL (tabla trabajos_pendientes con SELECT ... FOR UPDATE SKIP LOCKED) llega
// con la primera tarea real.
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/config"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/database"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	cfg, err := config.Cargar()
	if err != nil {
		slog.Error("worker", "error", err)
		os.Exit(1)
	}
	ctx, cancelar := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancelar()

	pool, err := database.Conectar(ctx, cfg.DatabaseURL)
	if err != nil {
		slog.Error("worker", "error", err)
		os.Exit(1)
	}
	defer pool.Close()

	slog.Info("worker iniciado", "entorno", cfg.Entorno)
	ciclo := time.NewTicker(30 * time.Second)
	defer ciclo.Stop()
	for {
		select {
		case <-ctx.Done():
			slog.Info("worker detenido")
			return
		case <-ciclo.C:
			if err := pool.Ping(ctx); err != nil {
				slog.Warn("worker sin base de datos", "error", err)
			}
		}
	}
}
