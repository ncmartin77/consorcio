package tests

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/google/uuid"

	"github.com/ncmartin77/consorcio/plataforma/internal/app"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/auth"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/config"
)

const clavePrueba = "clave-de-prueba-larga"

type cliente struct {
	t      *testing.T
	h      http.Handler
	cookie *http.Cookie
	ip     string
}

func (c *cliente) pedir(metodo, ruta, cuerpo string, csrf bool) *httptest.ResponseRecorder {
	c.t.Helper()
	req := httptest.NewRequest(metodo, ruta, strings.NewReader(cuerpo))
	req.RemoteAddr = c.ip + ":40000"
	if cuerpo != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	if csrf {
		req.Header.Set(auth.EncabezadoCSRF, "consorcios")
	}
	if c.cookie != nil {
		req.AddCookie(c.cookie)
	}
	rec := httptest.NewRecorder()
	c.h.ServeHTTP(rec, req)
	for _, ck := range rec.Result().Cookies() {
		if ck.Name == auth.NombreCookie {
			if ck.MaxAge < 0 {
				c.cookie = nil
			} else {
				c.cookie = ck
			}
		}
	}
	return rec
}

func (c *cliente) login(email, password string) int {
	c.t.Helper()
	cuerpo, _ := json.Marshal(map[string]string{"email": email, "password": password})
	return c.pedir(http.MethodPost, "/api/v1/sesion", string(cuerpo), true).Code
}

func TestSesionesYAislamientoPorHTTP(t *testing.T) {
	owner := conectar(t, "DATABASE_URL_OWNER")
	pool := conectar(t, "DATABASE_URL")
	ctx := context.Background()
	h := app.Rutas(config.Config{Entorno: "local"}, pool)

	hash, err := auth.HashPassword(clavePrueba)
	if err != nil {
		t.Fatal(err)
	}
	sufijo := uuid.NewString()[:8]
	emailA, emailB, emailInactivo := "a-"+sufijo+"@prueba.test", "b-"+sufijo+"@prueba.test", "x-"+sufijo+"@prueba.test"
	admA, admB := uuid.New(), uuid.New()
	usrA, usrB, usrX := uuid.New(), uuid.New(), uuid.New()
	for _, q := range []struct {
		sql  string
		args []any
	}{
		{`INSERT INTO administraciones (id, nombre) VALUES ($1, 'HTTP A'), ($2, 'HTTP B')`, []any{admA, admB}},
		{`INSERT INTO usuarios (id, email, nombre, password_hash, activo) VALUES
		    ($1, $4, 'Usuario A', $7, true), ($2, $5, 'Usuario B', $7, true), ($3, $6, 'Inactivo', $7, false)`,
			[]any{usrA, usrB, usrX, emailA, emailB, emailInactivo, hash}},
		{`INSERT INTO membresias (usuario_id, administracion_id, rol) VALUES ($1, $3, 'admin'), ($2, $4, 'consulta')`,
			[]any{usrA, usrB, admA, admB}},
		{`INSERT INTO consorcios (administracion_id, nombre) VALUES ($1, 'Edificio de A'), ($2, 'Edificio de B')`, []any{admA, admB}},
	} {
		if _, err := owner.Exec(ctx, q.sql, q.args...); err != nil {
			t.Fatal(err)
		}
	}
	t.Cleanup(func() {
		owner.Exec(ctx, `DELETE FROM consorcios WHERE administracion_id IN ($1, $2)`, admA, admB)
		owner.Exec(ctx, `DELETE FROM membresias WHERE administracion_id IN ($1, $2)`, admA, admB)
		owner.Exec(ctx, `DELETE FROM sesiones WHERE usuario_id IN ($1, $2, $3)`, usrA, usrB, usrX)
		owner.Exec(ctx, `DELETE FROM usuarios WHERE id IN ($1, $2, $3)`, usrA, usrB, usrX)
		owner.Exec(ctx, `DELETE FROM administraciones WHERE id IN ($1, $2)`, admA, admB)
	})

	t.Run("sin sesión no se entra", func(t *testing.T) {
		c := &cliente{t: t, h: h, ip: "198.51.100.1"}
		if code := c.pedir(http.MethodGet, "/api/v1/me", "", false).Code; code != http.StatusUnauthorized {
			t.Errorf("GET /me sin sesión: %d", code)
		}
		c.cookie = &http.Cookie{Name: auth.NombreCookie, Value: "inventada"}
		if code := c.pedir(http.MethodGet, "/api/v1/me", "", false).Code; code != http.StatusUnauthorized {
			t.Errorf("GET /me con cookie inventada: %d", code)
		}
	})

	t.Run("login sin encabezado CSRF se rechaza", func(t *testing.T) {
		c := &cliente{t: t, h: h, ip: "198.51.100.2"}
		cuerpo := `{"email":"` + emailA + `","password":"` + clavePrueba + `"}`
		if code := c.pedir(http.MethodPost, "/api/v1/sesion", cuerpo, false).Code; code != http.StatusForbidden {
			t.Errorf("login sin CSRF: %d", code)
		}
	})

	t.Run("contraseña incorrecta, email inexistente y usuario inactivo", func(t *testing.T) {
		c := &cliente{t: t, h: h, ip: "198.51.100.3"}
		for _, caso := range [][2]string{{emailA, "otra-clave-cualquiera"}, {"nadie-" + sufijo + "@prueba.test", clavePrueba}, {emailInactivo, clavePrueba}} {
			if code := c.login(caso[0], caso[1]); code != http.StatusUnauthorized {
				t.Errorf("login %s: %d", caso[0], code)
			}
		}
		if c.cookie != nil {
			t.Error("quedó una cookie de sesión tras logins fallidos")
		}
	})

	t.Run("login, me y logout", func(t *testing.T) {
		c := &cliente{t: t, h: h, ip: "198.51.100.4"}
		if code := c.login(strings.ToUpper(emailA), clavePrueba); code != http.StatusOK {
			t.Fatalf("login: %d", code)
		}
		if c.cookie == nil || !c.cookie.HttpOnly || c.cookie.SameSite != http.SameSiteLaxMode {
			t.Fatalf("cookie de sesión incorrecta: %+v", c.cookie)
		}
		var hashes int
		owner.QueryRow(ctx, `SELECT count(*) FROM sesiones WHERE usuario_id = $1 AND token_hash = sha256(convert_to($2, 'UTF8'))`,
			usrA, c.cookie.Value).Scan(&hashes)
		if hashes != 1 {
			t.Errorf("la base no tiene el SHA-256 del token (encontradas %d)", hashes)
		}
		rec := c.pedir(http.MethodGet, "/api/v1/me", "", false)
		if rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), emailA) {
			t.Errorf("GET /me: %d %s", rec.Code, rec.Body)
		}
		vieja := c.cookie
		if code := c.pedir(http.MethodDelete, "/api/v1/sesion", "", true).Code; code != http.StatusNoContent {
			t.Errorf("logout: %d", code)
		}
		c.cookie = vieja // reusar la cookie después del logout no tiene que servir
		if code := c.pedir(http.MethodGet, "/api/v1/me", "", false).Code; code != http.StatusUnauthorized {
			t.Errorf("cookie usada después del logout: %d", code)
		}
	})

	t.Run("cada usuario ve solo su administración", func(t *testing.T) {
		a := &cliente{t: t, h: h, ip: "198.51.100.5"}
		if code := a.login(emailA, clavePrueba); code != http.StatusOK {
			t.Fatalf("login A: %d", code)
		}
		rec := a.pedir(http.MethodGet, "/api/v1/me/administraciones", "", false)
		if !strings.Contains(rec.Body.String(), admA.String()) || strings.Contains(rec.Body.String(), admB.String()) {
			t.Errorf("administraciones de A: %s", rec.Body)
		}
		rec = a.pedir(http.MethodGet, "/api/v1/administraciones/"+admA.String()+"/consorcios", "", false)
		if rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), "Edificio de A") || strings.Contains(rec.Body.String(), "Edificio de B") {
			t.Errorf("consorcios de A: %d %s", rec.Code, rec.Body)
		}
		// La administración de B, por la ruta: 404 (ni siquiera revela que existe).
		if code := a.pedir(http.MethodGet, "/api/v1/administraciones/"+admB.String()+"/consorcios", "", false).Code; code != http.StatusNotFound {
			t.Errorf("A pidió los consorcios de B: %d", code)
		}
		if code := a.pedir(http.MethodPost, "/api/v1/administraciones/"+admB.String()+"/consorcios", `{"nombre":"intruso"}`, true).Code; code != http.StatusNotFound {
			t.Errorf("A creó un consorcio en B: %d", code)
		}
		if code := a.pedir(http.MethodPost, "/api/v1/administraciones/"+admA.String()+"/consorcios", `{"nombre":"Nuevo de A"}`, true).Code; code != http.StatusCreated {
			t.Errorf("A no pudo crear en su administración: %d", code)
		}
	})

	t.Run("rol consulta no puede crear", func(t *testing.T) {
		b := &cliente{t: t, h: h, ip: "198.51.100.6"}
		if code := b.login(emailB, clavePrueba); code != http.StatusOK {
			t.Fatalf("login B: %d", code)
		}
		if code := b.pedir(http.MethodPost, "/api/v1/administraciones/"+admB.String()+"/consorcios", `{"nombre":"x"}`, true).Code; code != http.StatusForbidden {
			t.Errorf("rol consulta creó un consorcio: %d", code)
		}
	})

	t.Run("demasiados intentos fallidos bloquean la IP", func(t *testing.T) {
		c := &cliente{t: t, h: h, ip: "198.51.100.7"}
		for i := 0; i < 10; i++ {
			c.login(emailA, "mal-mal-mal-mal")
		}
		if code := c.login(emailA, clavePrueba); code != http.StatusTooManyRequests {
			t.Errorf("tras 10 fallos, el login correcto dio %d (esperado 429)", code)
		}
	})

	t.Run("la aplicación no puede leer ni borrar la auditoría", func(t *testing.T) {
		var n int
		if err := owner.QueryRow(ctx, `SELECT count(*) FROM auditoria WHERE usuario_id = $1 AND accion = 'login'`, usrA).Scan(&n); err != nil || n == 0 {
			t.Errorf("no quedó registrado el login de A (n=%d, err=%v)", n, err)
		}
		if _, err := pool.Exec(ctx, `SELECT 1 FROM auditoria LIMIT 1`); err == nil {
			t.Error("el rol de la aplicación pudo leer la auditoría")
		}
		if _, err := pool.Exec(ctx, `DELETE FROM auditoria WHERE usuario_id = $1`, usrA); err == nil {
			t.Error("el rol de la aplicación pudo borrar la auditoría")
		}
	})
}

func TestPassword(t *testing.T) {
	if _, err := auth.HashPassword("corta"); err == nil {
		t.Error("aceptó una contraseña corta")
	}
	h1, _ := auth.HashPassword(clavePrueba)
	h2, _ := auth.HashPassword(clavePrueba)
	if h1 == h2 {
		t.Error("dos hashes iguales: falta sal aleatoria")
	}
	if ok, err := auth.VerificarPassword(clavePrueba, h1); !ok || err != nil {
		t.Errorf("no verifica la contraseña correcta: %v", err)
	}
	if ok, _ := auth.VerificarPassword("otra-clave-larga-x", h1); ok {
		t.Error("verificó una contraseña incorrecta")
	}
}
