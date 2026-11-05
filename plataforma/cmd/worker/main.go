// Worker de tareas asíncronas (PDF, tareas programadas, notificaciones).
//
// Por ahora: verifica la conexión y borra las sesiones vencidas en cada ciclo. La cola persistida en
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

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/auth"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/config"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/database"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
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
				continue
			}
			n, err := dbq.New(pool).BorrarSesionesVencidas(ctx, time.Now().Add(-auth.DuracionInactiva))
			if err != nil {
				slog.Warn("borrar sesiones vencidas", "error", err)
			} else if n > 0 {
				slog.Info("sesiones vencidas borradas", "cantidad", n)
			}
		}
	}
}
