// Package api tiene el armado común de los handlers del tenant: permisos, transacción
// con RLS, auditoría en la misma transacción y traducción de errores.
package api

import (
	"context"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/audit"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/auth"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/database"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/httpx"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/tenant"
)

// Tx da acceso a las consultas dentro de la transacción del tenant.
type Tx struct {
	Q   *dbq.Queries
	ctx context.Context
	t   tenant.Contexto
	r   *http.Request
}

// Auditar registra la acción en la misma transacción: si la operación se revierte,
// el registro también.
func (tx Tx) Auditar(accion string, detalle map[string]any) {
	uid, _ := auth.UsuarioID(tx.ctx)
	adm := tx.t.AdministracionID
	audit.Registrar(tx.ctx, tx.Q, audit.Evento{
		AdministracionID: &adm, UsuarioID: &uid, Accion: accion, Detalle: detalle, IP: auth.IPDe(tx.r),
	})
}

// Leer responde 200 con lo que devuelva fn (dentro de la transacción del tenant).
func Leer[T any](w http.ResponseWriter, r *http.Request, pool *pgxpool.Pool, que string, fn func(Tx) (T, error)) {
	responder(w, r, pool, http.StatusOK, que, false, fn)
}

// Escribir exige rol con permiso de escritura y responde con estado (201, 200...).
func Escribir[T any](w http.ResponseWriter, r *http.Request, pool *pgxpool.Pool, estado int, que string, fn func(Tx) (T, error)) {
	responder(w, r, pool, estado, que, true, fn)
}

func responder[T any](w http.ResponseWriter, r *http.Request, pool *pgxpool.Pool, estado int, que string, escribe bool, fn func(Tx) (T, error)) {
	t := tenant.Desde(r.Context())
	if escribe && !t.PuedeEscribir() {
		httpx.Error(w, http.StatusForbidden, "sin permiso")
		return
	}
	var res T
	err := database.EnTenant(r.Context(), pool, t.AdministracionID, func(ptx pgx.Tx) error {
		var err error
		res, err = fn(Tx{Q: dbq.New(ptx), ctx: r.Context(), t: t, r: r})
		return err
	})
	if err != nil {
		if e, ok := err.(*ErrorHTTP); ok {
			httpx.Error(w, e.Estado, e.Mensaje)
			return
		}
		httpx.ErrorDB(w, err, que)
		return
	}
	httpx.JSON(w, estado, res)
}

// ErrorHTTP corta la transacción con un error de validación para el usuario.
type ErrorHTTP struct {
	Estado  int
	Mensaje string
}

func (e *ErrorHTTP) Error() string { return e.Mensaje }

func Invalido(msg string) error  { return &ErrorHTTP{Estado: http.StatusBadRequest, Mensaje: msg} }
func Conflicto(msg string) error { return &ErrorHTTP{Estado: http.StatusConflict, Mensaje: msg} }

// ID lee un UUID de la ruta. Un ID mal formado es "inexistente" (404), igual que uno ajeno.
func ID(w http.ResponseWriter, r *http.Request, nombre, que string) (uuid.UUID, bool) {
	id, err := uuid.Parse(chi.URLParam(r, nombre))
	if err != nil {
		httpx.Error(w, http.StatusNotFound, que+" inexistente")
		return uuid.Nil, false
	}
	return id, true
}

// Lista evita devolver null en JSON cuando no hay filas.
func Lista[T any](v []T, err error) ([]T, error) {
	if v == nil {
		v = []T{}
	}
	return v, err
}

// EsAdmin: solo el rol admin aprueba, emite y reabre liquidaciones.
func (tx Tx) EsAdmin() bool { return tx.t.Rol == "admin" }

// Usuario de la sesión (para "creado_por").
func (tx Tx) Usuario() *uuid.UUID {
	uid, ok := auth.UsuarioID(tx.ctx)
	if !ok {
		return nil
	}
	return &uid
}

// Ctx de la transacción.
func (tx Tx) Ctx() context.Context { return tx.ctx }

func Prohibido(msg string) error { return &ErrorHTTP{Estado: http.StatusForbidden, Mensaje: msg} }
