// Package audit registra eventos en la tabla auditoria (solo agregado).
package audit

import (
	"context"
	"encoding/json"
	"log/slog"

	"github.com/google/uuid"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
)

type Evento struct {
	AdministracionID *uuid.UUID
	UsuarioID        *uuid.UUID
	Accion           string
	Detalle          map[string]any
	IP               string
}

// Registrar guarda el evento. Si falla, lo deja en el log y no corta la operación:
// la auditoría no debe impedir, por ejemplo, cerrar una sesión.
func Registrar(ctx context.Context, q *dbq.Queries, e Evento) {
	detalle := []byte("{}")
	if e.Detalle != nil {
		if b, err := json.Marshal(e.Detalle); err == nil {
			detalle = b
		}
	}
	var ip *string
	if e.IP != "" {
		ip = &e.IP
	}
	err := q.RegistrarAuditoria(ctx, dbq.RegistrarAuditoriaParams{
		AdministracionID: e.AdministracionID, UsuarioID: e.UsuarioID,
		Accion: e.Accion, Detalle: detalle, Ip: ip,
	})
	if err != nil {
		slog.Error("auditoría", "accion", e.Accion, "error", err)
	}
}
