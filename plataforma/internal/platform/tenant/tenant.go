// Package tenant resuelve la administración de cada request y verifica la membresía
// del usuario antes de que cualquier handler toque datos del tenant.
package tenant

import (
	"context"
	"errors"
	"log/slog"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/auth"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/httpx"
)

type Contexto struct {
	AdministracionID uuid.UUID
	Rol              string
}

// PuedeEscribir: los roles admin y operador modifican datos; consulta solo lee.
func (c Contexto) PuedeEscribir() bool { return c.Rol == "admin" || c.Rol == "operador" }

type claveCtx struct{}

func Desde(ctx context.Context) Contexto {
	return ctx.Value(claveCtx{}).(Contexto)
}

// Requerir toma {administracionID} de la ruta y lo acepta solo si el usuario de la
// sesión tiene membresía ahí. Nunca se confía en el ID que manda el navegador.
func Requerir(pool *pgxpool.Pool) func(http.Handler) http.Handler {
	q := dbq.New(pool)
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			usuarioID, ok := auth.UsuarioID(r.Context())
			if !ok {
				httpx.Error(w, http.StatusUnauthorized, "no autenticado")
				return
			}
			adminID, err := uuid.Parse(chi.URLParam(r, "administracionID"))
			if err != nil {
				httpx.Error(w, http.StatusNotFound, "administración inexistente")
				return
			}
			rol, err := q.RolEnAdministracion(r.Context(), dbq.RolEnAdministracionParams{
				UsuarioID: usuarioID, AdministracionID: adminID,
			})
			if errors.Is(err, pgx.ErrNoRows) {
				// 404 y no 403: no revelar que la administración existe.
				httpx.Error(w, http.StatusNotFound, "administración inexistente")
				return
			}
			if err != nil {
				slog.Error("verificar membresía", "error", err)
				httpx.Error(w, http.StatusInternalServerError, "error interno")
				return
			}
			ctx := context.WithValue(r.Context(), claveCtx{}, Contexto{AdministracionID: adminID, Rol: rol})
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}
