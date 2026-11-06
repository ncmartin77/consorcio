// Package httpx tiene ayudas comunes para los handlers HTTP/JSON.
package httpx

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

func JSON(w http.ResponseWriter, estado int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(estado)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		slog.Error("respuesta JSON", "error", err)
	}
}

func Error(w http.ResponseWriter, estado int, mensaje string) {
	JSON(w, estado, map[string]string{"error": mensaje})
}

// Leer decodifica el cuerpo JSON (máx. 1 MB) y rechaza campos desconocidos.
func Leer(w http.ResponseWriter, r *http.Request, v any) bool {
	dec := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20))
	dec.DisallowUnknownFields()
	if err := dec.Decode(v); err != nil {
		Error(w, http.StatusBadRequest, "cuerpo inválido: "+err.Error())
		return false
	}
	return true
}

// ErrorDB traduce errores de la base a respuestas HTTP con sentido para el usuario.
func ErrorDB(w http.ResponseWriter, err error, que string) {
	var pg *pgconn.PgError
	switch {
	case errors.Is(err, pgx.ErrNoRows):
		Error(w, http.StatusNotFound, que+" inexistente")
	case errors.As(err, &pg) && pg.Code == "23505": // unique_violation
		Error(w, http.StatusConflict, que+": ya existe")
	case errors.As(err, &pg) && pg.Code == "23P01": // exclusion_violation
		Error(w, http.StatusConflict, que+": se superpone en fechas con otro registro")
	case errors.As(err, &pg) && pg.Code == "23503": // foreign_key_violation
		Error(w, http.StatusNotFound, que+": hace referencia a algo inexistente")
	case errors.As(err, &pg) && (pg.Code == "23514" || pg.Code == "22P02" || pg.Code == "22003"): // check, formato, rango
		Error(w, http.StatusBadRequest, que+": datos inválidos")
	default:
		slog.Error(que, "error", err)
		Error(w, http.StatusInternalServerError, "error interno")
	}
}
