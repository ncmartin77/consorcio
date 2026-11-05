// Aplica las migraciones pendientes con el rol dueño del esquema (DATABASE_URL_OWNER).
package main

import (
	"context"
	"log/slog"
	"os"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/config"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/database"
)

func main() {
	cfg, err := config.Cargar()
	if err == nil {
		err = database.Migrar(context.Background(), cfg.DatabaseURLOwner)
	}
	if err != nil {
		slog.Error("migraciones", "error", err)
		os.Exit(1)
	}
}
