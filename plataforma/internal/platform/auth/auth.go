// Package auth identifica al usuario de cada request con sesiones HTTP.
//
//   - Login con email y contraseña (Argon2id). La cookie lleva un token aleatorio de
//     256 bits; en la base solo se guarda su SHA-256.
//   - La sesión vence a las 12 h o tras 2 h sin uso. Logout la borra.
//   - Cookie HttpOnly y SameSite=Lax; Secure fuera de APP_ENV=local.
//   - CSRF: todo pedido que modifica (POST, PUT, PATCH, DELETE) tiene que traer el
//     encabezado X-Requested-With, que otro sitio no puede mandar sin CORS.
//   - Intentos fallidos limitados por IP.
//
// Pendiente (Etapa 1): MFA para perfiles administrativos.
package auth

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/audit"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/httpx"
)

const (
	NombreCookie     = "consorcios_sesion"
	EncabezadoCSRF   = "X-Requested-With"
	DuracionMaxima   = 12 * time.Hour
	DuracionInactiva = 2 * time.Hour
	intervaloToque   = time.Minute
	maxFallosPorIP   = 10
	ventanaFallosIP  = 15 * time.Minute
)

type Usuario struct {
	ID     uuid.UUID `json:"id"`
	Email  string    `json:"email"`
	Nombre string    `json:"nombre"`
}

type claveCtx struct{}

func UsuarioID(ctx context.Context) (uuid.UUID, bool) {
	u, ok := ctx.Value(claveCtx{}).(Usuario)
	return u.ID, ok
}

func UsuarioDe(ctx context.Context) (Usuario, bool) {
	u, ok := ctx.Value(claveCtx{}).(Usuario)
	return u, ok
}

type Sesiones struct {
	pool   *pgxpool.Pool
	seguro bool // cookie Secure (todo menos APP_ENV=local, que corre en http://127.0.0.1)
	fallos *limitador
}

func NuevasSesiones(pool *pgxpool.Pool, entorno string) *Sesiones {
	return &Sesiones{pool: pool, seguro: entorno != "local", fallos: nuevoLimitador()}
}

// ExigirCSRF rechaza pedidos que modifican si no traen X-Requested-With.
func ExigirCSRF(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet, http.MethodHead, http.MethodOptions:
		default:
			if r.Header.Get(EncabezadoCSRF) == "" {
				httpx.Error(w, http.StatusForbidden, "falta el encabezado "+EncabezadoCSRF)
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}

type credenciales struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

// Login: POST /api/v1/sesion {"email","password"}.
func (s *Sesiones) Login(w http.ResponseWriter, r *http.Request) {
	ip := ipDe(r)
	if !s.fallos.permitido(ip) {
		httpx.Error(w, http.StatusTooManyRequests, "demasiados intentos; probá más tarde")
		return
	}
	var c credenciales
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4096)).Decode(&c); err != nil ||
		strings.TrimSpace(c.Email) == "" || c.Password == "" {
		httpx.Error(w, http.StatusBadRequest, "faltan email o contraseña")
		return
	}
	q := dbq.New(s.pool)
	ctx := r.Context()

	u, err := q.UsuarioPorEmail(ctx, strings.TrimSpace(c.Email))
	if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		slog.Error("login: buscar usuario", "error", err)
		httpx.Error(w, http.StatusInternalServerError, "error interno")
		return
	}
	hash := hashFicticio
	if err == nil && u.PasswordHash != nil {
		hash = *u.PasswordHash
	}
	ok, errVerif := VerificarPassword(c.Password, hash)
	if errVerif != nil {
		slog.Error("login: verificar contraseña", "error", errVerif)
	}
	if err != nil || u.PasswordHash == nil || !u.Activo || !ok {
		s.fallos.fallo(ip)
		var uid *uuid.UUID
		if err == nil {
			uid = &u.ID
		}
		audit.Registrar(ctx, q, audit.Evento{UsuarioID: uid, Accion: "login_fallido",
			Detalle: map[string]any{"email": strings.ToLower(strings.TrimSpace(c.Email))}, IP: ip})
		httpx.Error(w, http.StatusUnauthorized, "email o contraseña incorrectos")
		return
	}

	token, hashToken, err := nuevoToken()
	if err != nil {
		slog.Error("login: token", "error", err)
		httpx.Error(w, http.StatusInternalServerError, "error interno")
		return
	}
	vence := time.Now().Add(DuracionMaxima)
	ua := r.UserAgent()
	if len(ua) > 300 {
		ua = ua[:300]
	}
	if err := q.CrearSesion(ctx, dbq.CrearSesionParams{
		TokenHash: hashToken, UsuarioID: u.ID, VenceEn: vence, Ip: &ip, UserAgent: &ua,
	}); err != nil {
		slog.Error("login: crear sesión", "error", err)
		httpx.Error(w, http.StatusInternalServerError, "error interno")
		return
	}
	s.fallos.limpiar(ip)
	audit.Registrar(ctx, q, audit.Evento{UsuarioID: &u.ID, Accion: "login", IP: ip})

	http.SetCookie(w, &http.Cookie{
		Name: NombreCookie, Value: token, Path: "/", Expires: vence,
		HttpOnly: true, Secure: s.seguro, SameSite: http.SameSiteLaxMode,
	})
	httpx.JSON(w, http.StatusOK, Usuario{ID: u.ID, Email: u.Email, Nombre: u.Nombre})
}

// Logout: DELETE /api/v1/sesion (con sesión).
func (s *Sesiones) Logout(w http.ResponseWriter, r *http.Request) {
	if ck, err := r.Cookie(NombreCookie); err == nil {
		q := dbq.New(s.pool)
		if err := q.BorrarSesion(r.Context(), hashDe(ck.Value)); err != nil {
			slog.Error("logout", "error", err)
		}
		if u, ok := UsuarioDe(r.Context()); ok {
			audit.Registrar(r.Context(), q, audit.Evento{UsuarioID: &u.ID, Accion: "logout", IP: ipDe(r)})
		}
	}
	http.SetCookie(w, &http.Cookie{
		Name: NombreCookie, Value: "", Path: "/", MaxAge: -1,
		HttpOnly: true, Secure: s.seguro, SameSite: http.SameSiteLaxMode,
	})
	w.WriteHeader(http.StatusNoContent)
}

// Requerir deja pasar solo con una sesión vigente y pone al usuario en el contexto.
func (s *Sesiones) Requerir(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ck, err := r.Cookie(NombreCookie)
		if err != nil || ck.Value == "" {
			httpx.Error(w, http.StatusUnauthorized, "no autenticado")
			return
		}
		h := hashDe(ck.Value)
		q := dbq.New(s.pool)
		ses, err := q.SesionVigente(r.Context(), dbq.SesionVigenteParams{
			TokenHash: h, UsadaDesde: time.Now().Add(-DuracionInactiva),
		})
		if errors.Is(err, pgx.ErrNoRows) {
			httpx.Error(w, http.StatusUnauthorized, "no autenticado")
			return
		}
		if err != nil {
			slog.Error("validar sesión", "error", err)
			httpx.Error(w, http.StatusInternalServerError, "error interno")
			return
		}
		if time.Since(ses.UltimoUso) > intervaloToque {
			if err := q.TocarSesion(r.Context(), h); err != nil {
				slog.Warn("actualizar uso de sesión", "error", err)
			}
		}
		u := Usuario{ID: ses.UsuarioID, Email: ses.Email, Nombre: ses.Nombre}
		next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), claveCtx{}, u)))
	})
}

func nuevoToken() (token string, hash []byte, err error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", nil, err
	}
	token = base64.RawURLEncoding.EncodeToString(b)
	return token, hashDe(token), nil
}

func hashDe(token string) []byte {
	h := sha256.Sum256([]byte(token))
	return h[:]
}

// ipDe usa la dirección de la conexión. Detrás de Nginx habrá que tomarla de
// X-Forwarded-For solo si viene del proxy de confianza.
func ipDe(r *http.Request) string {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

// limitador cuenta intentos fallidos por IP en una ventana fija (en memoria: alcanza
// con una sola instancia de la API).
type limitador struct {
	mu     sync.Mutex
	fallas map[string][]time.Time
}

func nuevoLimitador() *limitador { return &limitador{fallas: map[string][]time.Time{}} }

func (l *limitador) recientes(ip string) []time.Time {
	desde := time.Now().Add(-ventanaFallosIP)
	v := l.fallas[ip][:0]
	for _, t := range l.fallas[ip] {
		if t.After(desde) {
			v = append(v, t)
		}
	}
	if len(v) == 0 {
		delete(l.fallas, ip)
		return nil
	}
	l.fallas[ip] = v
	return v
}

func (l *limitador) permitido(ip string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	return len(l.recientes(ip)) < maxFallosPorIP
}

func (l *limitador) fallo(ip string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.fallas[ip] = append(l.recientes(ip), time.Now())
}

func (l *limitador) limpiar(ip string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	delete(l.fallas, ip)
}
