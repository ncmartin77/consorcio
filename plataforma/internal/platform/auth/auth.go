// Package auth identifica al usuario de cada request.
//
// Esqueleto: las sesiones HTTP con Argon2id y MFA son el próximo paso de la Etapa 1.
// Mientras tanto, solo con APP_ENV=local se acepta el encabezado X-Usuario-Dev (UUID
// de un usuario existente) para probar la API. En cualquier otro entorno responde 401.
package auth

import (
	"context"
	"errors"
	"net/http"

	"github.com/google/uuid"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/httpx"
)

type claveCtx struct{}

func UsuarioID(ctx context.Context) (uuid.UUID, bool) {
	id, ok := ctx.Value(claveCtx{}).(uuid.UUID)
	return id, ok
}

func Requerir(entorno string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			var id uuid.UUID
			err := errors.New("sin sesión")
			if entorno == "local" {
				id, err = uuid.Parse(r.Header.Get("X-Usuario-Dev"))
			}
			if err != nil {
				httpx.Error(w, http.StatusUnauthorized, "no autenticado")
				return
			}
			next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), claveCtx{}, id)))
		})
	}
}
