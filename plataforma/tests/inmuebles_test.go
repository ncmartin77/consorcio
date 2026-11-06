package tests

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"testing"

	"github.com/google/uuid"
	"github.com/shopspring/decimal"

	"github.com/ncmartin77/consorcio/plataforma/internal/app"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/auth"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/config"
	"github.com/ncmartin77/consorcio/plataforma/internal/prorrateo"
)

// escenario: administraciones A y B; usuario A (admin de A), B (admin de B) y
// C (consulta en A), ya logueados.
type escenario struct {
	admA, admB uuid.UUID
	a, b, c    *cliente
}

func armarEscenario(t *testing.T) escenario {
	t.Helper()
	owner := conectar(t, "DATABASE_URL_OWNER")
	pool := conectar(t, "DATABASE_URL")
	ctx := context.Background()
	h := app.Rutas(config.Config{Entorno: "local"}, pool)
	hash, _ := auth.HashPassword(clavePrueba)
	suf := uuid.NewString()[:8]
	e := escenario{admA: uuid.New(), admB: uuid.New()}
	ua, ub, uc := uuid.New(), uuid.New(), uuid.New()
	for _, q := range []struct {
		sql  string
		args []any
	}{
		{`INSERT INTO administraciones (id, nombre) VALUES ($1, 'Inm A'), ($2, 'Inm B')`, []any{e.admA, e.admB}},
		{`INSERT INTO usuarios (id, email, nombre, password_hash) VALUES ($1, $4, 'A', $7), ($2, $5, 'B', $7), ($3, $6, 'C', $7)`,
			[]any{ua, ub, uc, "ia-" + suf + "@prueba.test", "ib-" + suf + "@prueba.test", "ic-" + suf + "@prueba.test", hash}},
		{`INSERT INTO membresias (usuario_id, administracion_id, rol) VALUES ($1, $4, 'admin'), ($2, $5, 'admin'), ($3, $4, 'consulta')`,
			[]any{ua, ub, uc, e.admA, e.admB}},
	} {
		if _, err := owner.Exec(ctx, q.sql, q.args...); err != nil {
			t.Fatal(err)
		}
	}
	t.Cleanup(func() {
		adms := []any{e.admA, e.admB}
		for _, tabla := range []string{"unidad_coeficientes", "grupos_prorrateo", "unidad_personas", "personas", "unidades", "consorcios", "membresias"} {
			if _, err := owner.Exec(ctx, "DELETE FROM "+tabla+" WHERE administracion_id IN ($1, $2)", adms...); err != nil {
				t.Errorf("limpiar %s: %v", tabla, err)
			}
		}
		owner.Exec(ctx, `DELETE FROM sesiones WHERE usuario_id IN ($1, $2, $3)`, ua, ub, uc)
		owner.Exec(ctx, `DELETE FROM usuarios WHERE id IN ($1, $2, $3)`, ua, ub, uc)
		owner.Exec(ctx, `DELETE FROM administraciones WHERE id IN ($1, $2)`, adms...)
	})
	for i, x := range []struct {
		c     **cliente
		email string
	}{{&e.a, "ia-"}, {&e.b, "ib-"}, {&e.c, "ic-"}} {
		*x.c = &cliente{t: t, h: h, ip: fmt.Sprintf("203.0.113.%d", 10+i)}
		if code := (*x.c).login(x.email+suf+"@prueba.test", clavePrueba); code != http.StatusOK {
			t.Fatalf("login %s: %d", x.email, code)
		}
	}
	return e
}

// json helpers
func (c *cliente) enviar(metodo, ruta string, cuerpo any) (int, map[string]any) {
	c.t.Helper()
	b := ""
	if cuerpo != nil {
		j, _ := json.Marshal(cuerpo)
		b = string(j)
	}
	rec := c.pedir(metodo, ruta, b, metodo != http.MethodGet)
	var m map[string]any
	json.Unmarshal(rec.Body.Bytes(), &m)
	return rec.Code, m
}

func (c *cliente) lista(ruta string) (int, []map[string]any) {
	c.t.Helper()
	rec := c.pedir(http.MethodGet, ruta, "", false)
	var l []map[string]any
	json.Unmarshal(rec.Body.Bytes(), &l)
	return rec.Code, l
}

func esperar(t *testing.T, que string, obtenido, esperado int, cuerpo ...map[string]any) {
	t.Helper()
	if obtenido != esperado {
		t.Errorf("%s: HTTP %d, esperado %d %v", que, obtenido, esperado, cuerpo)
	}
}

func TestInmueblesYPersonas(t *testing.T) {
	e := armarEscenario(t)
	A := "/api/v1/administraciones/" + e.admA.String()
	B := "/api/v1/administraciones/" + e.admB.String()

	code, cons := e.a.enviar(http.MethodPost, A+"/consorcios", map[string]any{"nombre": "Brasil 376"})
	esperar(t, "crear consorcio", code, http.StatusCreated, cons)
	consA := cons["id"].(string)
	code, cons2 := e.a.enviar(http.MethodPost, A+"/consorcios", map[string]any{"nombre": "Otro edificio"})
	esperar(t, "crear segundo consorcio", code, http.StatusCreated, cons2)
	consA2 := cons2["id"].(string)

	unidades := map[string]string{}
	for _, u := range []map[string]any{
		{"codigo": "1", "descripcion": "Dpto 1 - PB", "piso": "PB"},
		{"codigo": "2", "tipo": "cochera"},
		{"codigo": "3", "piso": "1"},
	} {
		code, m := e.a.enviar(http.MethodPost, A+"/consorcios/"+consA+"/unidades", u)
		esperar(t, "crear unidad "+u["codigo"].(string), code, http.StatusCreated, m)
		unidades[u["codigo"].(string)] = m["id"].(string)
	}
	_, ajena := e.a.enviar(http.MethodPost, A+"/consorcios/"+consA2+"/unidades", map[string]any{"codigo": "1"})
	unidadOtroConsorcio := ajena["id"].(string)

	t.Run("validaciones de unidades", func(t *testing.T) {
		code, _ := e.a.enviar(http.MethodPost, A+"/consorcios/"+consA+"/unidades", map[string]any{"codigo": "1"})
		esperar(t, "código repetido", code, http.StatusConflict)
		code, _ = e.a.enviar(http.MethodPost, A+"/consorcios/"+consA+"/unidades", map[string]any{"codigo": "9", "tipo": "castillo"})
		esperar(t, "tipo inválido", code, http.StatusBadRequest)
		code, _ = e.a.enviar(http.MethodPost, A+"/consorcios/"+consA+"/unidades", map[string]any{"codigo": "9", "campo_raro": 1})
		esperar(t, "campo desconocido", code, http.StatusBadRequest)
		code, m := e.a.enviar(http.MethodPatch, A+"/unidades/"+unidades["3"], map[string]any{"activa": false})
		esperar(t, "desactivar unidad", code, http.StatusOK, m)
		if m["activa"] != false || m["piso"] != "1" {
			t.Errorf("PATCH cambió de más o de menos: %v", m)
		}
		code, l := e.a.lista(A + "/consorcios/" + consA + "/unidades")
		if code != http.StatusOK || len(l) != 3 {
			t.Errorf("listar unidades: %d, %d filas", code, len(l))
		}
	})

	t.Run("rol consulta lee pero no escribe", func(t *testing.T) {
		code, _ := e.c.lista(A + "/consorcios/" + consA + "/unidades")
		esperar(t, "consulta lee", code, http.StatusOK)
		code, _ = e.c.enviar(http.MethodPost, A+"/consorcios/"+consA+"/unidades", map[string]any{"codigo": "99"})
		esperar(t, "consulta crea unidad", code, http.StatusForbidden)
		code, _ = e.c.enviar(http.MethodPost, A+"/personas", map[string]any{"nombre": "X"})
		esperar(t, "consulta crea persona", code, http.StatusForbidden)
	})

	// Personas y vínculos con historia.
	_, ana := e.a.enviar(http.MethodPost, A+"/personas", map[string]any{"nombre": "Ana Pérez", "documento": "20111222"})
	_, juan := e.a.enviar(http.MethodPost, A+"/personas", map[string]any{"nombre": "Juan Gómez"})
	anaID, juanID := ana["id"].(string), juan["id"].(string)
	u1 := A + "/unidades/" + unidades["1"] + "/vinculos"

	t.Run("vínculos con historia", func(t *testing.T) {
		code, vAna := e.a.enviar(http.MethodPost, u1, map[string]any{
			"persona_id": anaID, "tipo_vinculo": "propietario", "porcentaje_titularidad": "100", "desde": "2020-01-01"})
		esperar(t, "Ana propietaria", code, http.StatusCreated, vAna)
		code, _ = e.a.enviar(http.MethodPost, u1, map[string]any{"persona_id": anaID, "tipo_vinculo": "propietario", "desde": "2024-05-01"})
		esperar(t, "vínculo superpuesto", code, http.StatusConflict)
		code, _ = e.a.enviar(http.MethodPost, u1, map[string]any{
			"persona_id": juanID, "tipo_vinculo": "inquilino", "porcentaje_titularidad": "50", "desde": "2024-01-01"})
		esperar(t, "inquilino con titularidad", code, http.StatusBadRequest)
		code, _ = e.a.enviar(http.MethodPost, u1, map[string]any{"persona_id": anaID, "tipo_vinculo": "propietario", "desde": "1-1-2020"})
		esperar(t, "fecha mal escrita", code, http.StatusBadRequest)

		// Ana vende el 01/07/2026 a Juan.
		fin := A + "/vinculos/" + vAna["id"].(string) + "/finalizar"
		code, m := e.a.enviar(http.MethodPost, fin, map[string]any{"hasta": "2026-07-01"})
		esperar(t, "finalizar Ana", code, http.StatusOK, m)
		code, _ = e.a.enviar(http.MethodPost, fin, map[string]any{"hasta": "2026-08-01"})
		esperar(t, "finalizar dos veces", code, http.StatusNotFound)
		code, m = e.a.enviar(http.MethodPost, u1, map[string]any{
			"persona_id": juanID, "tipo_vinculo": "propietario", "porcentaje_titularidad": "100", "desde": "2026-07-01", "recibe_liquidacion": true})
		esperar(t, "Juan propietario", code, http.StatusCreated, m)

		for fechaQ, quien := range map[string]string{"2026-06-30": "Ana Pérez", "2026-07-01": "Juan Gómez"} {
			_, l := e.a.lista(u1 + "?fecha=" + fechaQ)
			if len(l) != 1 || l[0]["persona_nombre"] != quien {
				t.Errorf("propietario al %s: %v", fechaQ, l)
			}
		}
		if _, l := e.a.lista(u1 + "?historial=1"); len(l) != 2 {
			t.Errorf("historial: %d vínculos", len(l))
		}
		if _, l := e.a.lista(A + "/personas/" + anaID + "/vinculos"); len(l) != 1 || l[0]["hasta"] != "2026-07-01" {
			t.Errorf("vínculos de Ana: %v", l)
		}
		if _, l := e.a.lista(A + "/personas?q=pérez"); len(l) != 1 {
			t.Errorf("búsqueda por nombre: %v", l)
		}
	})

	// Prorrateo.
	code, g := e.a.enviar(http.MethodPost, A+"/consorcios/"+consA+"/grupos", map[string]any{"nombre": "GENERAL"})
	esperar(t, "crear grupo", code, http.StatusCreated, g)
	coefs := A + "/grupos/" + g["id"].(string) + "/coeficientes"
	tabla := func(desde string, p1, p2, p3 string) map[string]any {
		return map[string]any{"vigente_desde": desde, "coeficientes": []map[string]any{
			{"unidad_id": unidades["1"], "porcentaje": p1},
			{"unidad_id": unidades["2"], "porcentaje": p2},
			{"unidad_id": unidades["3"], "porcentaje": p3},
		}}
	}

	t.Run("coeficientes con vigencia", func(t *testing.T) {
		code, m := e.a.enviar(http.MethodPut, coefs, tabla("2026-01-01", "33.333334", "33.333333", "33.333334"))
		esperar(t, "suma 100,000001", code, http.StatusBadRequest, m)
		code, _ = e.a.enviar(http.MethodPut, coefs, tabla("2026-01-01", "33.3333333", "33.333333", "33.3333337"))
		esperar(t, "más de 6 decimales", code, http.StatusBadRequest)
		dup := tabla("2026-01-01", "50", "50", "0")
		dup["coeficientes"].([]map[string]any)[1]["unidad_id"] = unidades["1"]
		code, _ = e.a.enviar(http.MethodPut, coefs, dup)
		esperar(t, "unidad repetida", code, http.StatusBadRequest)
		otro := tabla("2026-01-01", "50", "50", "0")
		otro["coeficientes"].([]map[string]any)[2]["unidad_id"] = unidadOtroConsorcio
		code, _ = e.a.enviar(http.MethodPut, coefs, otro)
		esperar(t, "unidad de otro consorcio", code, http.StatusNotFound)

		code, m = e.a.enviar(http.MethodPut, coefs, tabla("2026-01-01", "33.333334", "33.333333", "33.333333"))
		esperar(t, "tabla de enero", code, http.StatusOK, m)
		if m["suma_correcta"] != true || m["suma"] != "100" {
			t.Errorf("suma de la tabla de enero: %v / %v", m["suma"], m["suma_correcta"])
		}
		code, _ = e.a.enviar(http.MethodPut, coefs, tabla("2025-12-01", "40", "30", "30"))
		esperar(t, "tabla anterior a la vigente", code, http.StatusConflict)
		code, _ = e.a.enviar(http.MethodPut, coefs, tabla("2026-07-01", "50", "20", "30"))
		esperar(t, "tabla de julio", code, http.StatusOK)

		porc := func(fecha string) string {
			_, m := e.a.enviar(http.MethodGet, coefs+"?fecha="+fecha, nil)
			cs, _ := m["coeficientes"].([]any)
			if len(cs) != 3 {
				return fmt.Sprintf("%d coeficientes", len(cs))
			}
			return cs[0].(map[string]any)["porcentaje"].(string)
		}
		if p := porc("2026-06-30"); p != "33.333334" {
			t.Errorf("unidad 1 al 30/06: %s", p)
		}
		if p := porc("2026-07-01"); p != "50" {
			t.Errorf("unidad 1 al 01/07: %s", p)
		}
		if p := porc("2025-12-31"); p != "0 coeficientes" {
			t.Errorf("antes de la primera tabla: %s", p)
		}
	})

	t.Run("otra administración no ve ni toca nada de A", func(t *testing.T) {
		for _, ruta := range []string{
			A + "/consorcios/" + consA, // por la ruta de A: no es miembro
			B + "/consorcios/" + consA, // por la ruta propia, con IDs de A
			B + "/consorcios/" + consA + "/unidades",
			B + "/unidades/" + unidades["1"],
			B + "/unidades/" + unidades["1"] + "/vinculos?historial=1",
			B + "/personas/" + anaID,
			B + "/personas/" + anaID + "/vinculos",
			B + "/grupos/" + g["id"].(string) + "/coeficientes",
			B + "/consorcios/" + consA + "/grupos",
		} {
			if code, _ := e.b.enviar(http.MethodGet, ruta, nil); code != http.StatusNotFound {
				t.Errorf("B GET %s: %d (esperado 404)", strings.TrimPrefix(ruta, "/api/v1"), code)
			}
		}
		if _, l := e.b.lista(B + "/personas?q=ana"); len(l) != 0 {
			t.Errorf("B encuentra personas de A: %v", l)
		}
		escrituras := []struct {
			metodo, ruta string
			cuerpo       any
		}{
			{http.MethodPost, B + "/consorcios/" + consA + "/unidades", map[string]any{"codigo": "intrusa"}},
			{http.MethodPatch, B + "/unidades/" + unidades["1"], map[string]any{"activa": false}},
			{http.MethodPatch, B + "/personas/" + anaID, map[string]any{"nombre": "pisado"}},
			{http.MethodPost, B + "/consorcios/" + consA + "/grupos", map[string]any{"nombre": "intruso"}},
			{http.MethodPut, B + "/grupos/" + g["id"].(string) + "/coeficientes", tabla("2027-01-01", "100", "0", "0")},
		}
		for _, w := range escrituras {
			if code, _ := e.b.enviar(w.metodo, w.ruta, w.cuerpo); code != http.StatusNotFound {
				t.Errorf("B %s %s: %d (esperado 404)", w.metodo, strings.TrimPrefix(w.ruta, "/api/v1"), code)
			}
		}
		// B con una unidad propia intenta vincular a una persona de A.
		_, consB := e.b.enviar(http.MethodPost, B+"/consorcios", map[string]any{"nombre": "Edificio B"})
		_, uB := e.b.enviar(http.MethodPost, B+"/consorcios/"+consB["id"].(string)+"/unidades", map[string]any{"codigo": "1"})
		code, _ := e.b.enviar(http.MethodPost, B+"/unidades/"+uB["id"].(string)+"/vinculos",
			map[string]any{"persona_id": anaID, "tipo_vinculo": "propietario", "desde": "2026-01-01"})
		esperar(t, "B vincula persona de A", code, http.StatusNotFound)
		// Y nada de A cambió.
		if _, m := e.a.enviar(http.MethodGet, A+"/personas/"+anaID, nil); m["nombre"] != "Ana Pérez" {
			t.Errorf("la persona de A cambió: %v", m)
		}
	})
}

func TestValidarTablaCoeficientes(t *testing.T) {
	u := func() uuid.UUID { return uuid.New() }
	casos := []struct {
		nombre string
		cs     []prorrateo.Coeficiente
		ok     bool
	}{
		{"vacía", nil, false},
		{"suma 100", []prorrateo.Coeficiente{{UnidadID: u(), Porcentaje: dec("60")}, {UnidadID: u(), Porcentaje: dec("40")}}, true},
		{"suma 100,001 como en el sistema actual", []prorrateo.Coeficiente{{UnidadID: u(), Porcentaje: dec("60.001")}, {UnidadID: u(), Porcentaje: dec("40")}}, false},
		{"negativo", []prorrateo.Coeficiente{{UnidadID: u(), Porcentaje: dec("110")}, {UnidadID: u(), Porcentaje: dec("-10")}}, false},
	}
	for _, c := range casos {
		if err := prorrateo.ValidarTabla(c.cs); (err == nil) != c.ok {
			t.Errorf("%s: err=%v", c.nombre, err)
		}
	}
}

func dec(s string) decimal.Decimal { return decimal.RequireFromString(s) }
