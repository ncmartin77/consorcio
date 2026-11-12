package tests

import (
	"context"
	"net/http"
	"testing"
)

// Flujo completo de la etapa 3 por HTTP, con importes calculados a mano:
// parámetros, tasa, gastos (ordinarios, extraordinarios y pagados con el fondo), cargos,
// deuda inicial, calcular, condonar, aprobar, emitir, pagos con imputación y saldo a favor,
// interés del mes siguiente, reabrir y aislamiento entre administraciones.
func TestLiquidaciones(t *testing.T) {
	e := armarEscenario(t)
	A := "/api/v1/administraciones/" + e.admA.String()
	B := "/api/v1/administraciones/" + e.admB.String()
	ctx := context.Background()
	owner := conectar(t, "DATABASE_URL_OWNER")
	t.Cleanup(func() {
		adm := e.admA
		for _, q := range []string{
			"DELETE FROM aplicaciones WHERE administracion_id = $1",
			"DELETE FROM pagos WHERE administracion_id = $1",
			"DELETE FROM partidas WHERE administracion_id = $1",
			"DELETE FROM liquidacion_condonaciones WHERE administracion_id = $1",
			"UPDATE liquidaciones SET calculo_id = NULL, estado = 'borrador', vencimiento = NULL, emitida_en = NULL WHERE administracion_id = $1",
			"DELETE FROM liquidacion_calculos WHERE administracion_id = $1",
			"DELETE FROM liquidaciones WHERE administracion_id = $1",
			"DELETE FROM cargos_particulares WHERE administracion_id = $1",
			"DELETE FROM gastos WHERE administracion_id = $1",
			"DELETE FROM tasas_mora WHERE administracion_id = $1",
			"DELETE FROM parametros_consorcio WHERE administracion_id = $1",
		} {
			if _, err := owner.Exec(ctx, q, adm); err != nil {
				t.Errorf("limpiar: %s: %v", q, err)
			}
		}
	})

	ok := func(que string, code, esperado int, m map[string]any) map[string]any {
		t.Helper()
		esperar(t, que, code, esperado, m)
		return m
	}
	igual := func(que string, obtenido any, esperado string) {
		t.Helper()
		if s, _ := obtenido.(string); s != esperado {
			t.Errorf("%s: obtenido %v, esperado %s", que, obtenido, esperado)
		}
	}

	// ── Armado: consorcio, 3 unidades, grupos GENERAL y Ascensor ──
	code, cons := e.a.enviar(http.MethodPost, A+"/consorcios", map[string]any{"nombre": "Perú 376"})
	cid := ok("consorcio", code, http.StatusCreated, cons)["id"].(string)
	C := A + "/consorcios/" + cid
	u := map[string]string{}
	for _, cod := range []string{"1", "2", "3"} {
		code, m := e.a.enviar(http.MethodPost, C+"/unidades", map[string]any{"codigo": cod})
		u[cod] = ok("unidad "+cod, code, http.StatusCreated, m)["id"].(string)
	}
	code, g := e.a.enviar(http.MethodPost, C+"/grupos", map[string]any{"nombre": "GENERAL"})
	general := ok("grupo GENERAL", code, http.StatusCreated, g)["id"].(string)
	code, g = e.a.enviar(http.MethodPost, C+"/grupos", map[string]any{"nombre": "Ascensor"})
	ascensor := ok("grupo Ascensor", code, http.StatusCreated, g)["id"].(string)
	code, m := e.a.enviar(http.MethodPut, A+"/grupos/"+general+"/coeficientes", map[string]any{
		"vigente_desde": "2026-01-01", "coeficientes": []map[string]any{
			{"unidad_id": u["1"], "porcentaje": "33.333334"}, {"unidad_id": u["2"], "porcentaje": "33.333333"},
			{"unidad_id": u["3"], "porcentaje": "33.333333"}}})
	ok("coeficientes GENERAL", code, http.StatusOK, m)
	code, m = e.a.enviar(http.MethodPut, A+"/grupos/"+ascensor+"/coeficientes", map[string]any{
		"vigente_desde": "2026-01-01", "coeficientes": []map[string]any{
			{"unidad_id": u["1"], "porcentaje": "50"}, {"unidad_id": u["2"], "porcentaje": "50"}}})
	ok("coeficientes Ascensor", code, http.StatusOK, m)

	// ── Liquidación de octubre (gastos de septiembre) ──
	code, liq := e.a.enviar(http.MethodPost, C+"/liquidaciones", map[string]any{"periodo": "2026-10-01"})
	oct := ok("crear liquidación oct", code, http.StatusCreated, liq)["id"].(string)
	L := A + "/liquidaciones/"

	t.Run("sin parámetros ni tasa no calcula", func(t *testing.T) {
		code, m := e.a.enviar(http.MethodPost, L+oct+"/calcular", nil)
		esperar(t, "calcular sin parámetros", code, http.StatusConflict, m)
	})

	code, m = e.a.enviar(http.MethodPost, C+"/parametros", map[string]any{
		"vigente_desde": "2026-09-01", "dia_vencimiento": 10, "fondo_reserva_mensual": "3000", "grupo_fondo_id": general})
	ok("parámetros", code, http.StatusCreated, m)
	code, m = e.a.enviar(http.MethodPost, C+"/tasas-mora", map[string]any{
		"vigente_desde": "2026-09-01", "tasa_mensual": "0.03", "fundamento": "Reglamento art. 12"})
	ok("tasa", code, http.StatusCreated, m)

	t.Run("validaciones", func(t *testing.T) {
		code, _ := e.a.enviar(http.MethodPost, C+"/tasas-mora", map[string]any{"vigente_desde": "2026-12-01", "tasa_mensual": "0.03"})
		esperar(t, "tasa sin fundamento", code, http.StatusBadRequest)
		code, _ = e.a.enviar(http.MethodPost, C+"/tasas-mora", map[string]any{"vigente_desde": "2026-12-15", "tasa_mensual": "0.03", "fundamento": "x"})
		esperar(t, "tasa que no empieza el día 1", code, http.StatusBadRequest)
		code, _ = e.a.enviar(http.MethodPost, C+"/gastos", map[string]any{"periodo": "2026-09-01", "grupo_id": general,
			"concepto": "Pintura", "importe": "100", "naturaleza": "extraordinaria"})
		esperar(t, "extraordinario sin respaldo", code, http.StatusBadRequest)
		code, _ = e.a.enviar(http.MethodPost, C+"/gastos", map[string]any{"periodo": "2026-09-01", "grupo_id": general,
			"concepto": "X", "importe": "1.001"})
		esperar(t, "importe con 3 decimales", code, http.StatusBadRequest)
		code, _ = e.c.enviar(http.MethodPost, C+"/gastos", map[string]any{"periodo": "2026-09-01", "grupo_id": general,
			"concepto": "X", "importe": "1"})
		esperar(t, "rol consulta no carga gastos", code, http.StatusForbidden)
		code, _ = e.a.enviar(http.MethodPost, C+"/liquidaciones", map[string]any{"periodo": "2026-10-01"})
		esperar(t, "liquidación repetida", code, http.StatusConflict)
	})

	for _, gs := range []map[string]any{
		{"periodo": "2026-09-01", "grupo_id": general, "concepto": "Sueldos y cargas", "importe": "100000"},
		{"periodo": "2026-09-01", "grupo_id": ascensor, "concepto": "Abono ascensor", "importe": "20001"},
		{"periodo": "2026-09-01", "grupo_id": general, "concepto": "Impermeabilización", "importe": "9000",
			"naturaleza": "extraordinaria", "habitualidad": "no_recurrente", "respaldo": "Acta de asamblea 5"},
		{"periodo": "2026-09-01", "grupo_id": general, "concepto": "Bomba de agua (fondo)", "importe": "50000",
			"financiacion": "fondo_reserva"},
	} {
		code, m := e.a.enviar(http.MethodPost, C+"/gastos", gs)
		ok("gasto "+gs["concepto"].(string), code, http.StatusCreated, m)
	}
	code, m = e.a.enviar(http.MethodPost, C+"/cargos", map[string]any{"unidad_id": u["3"], "periodo": "2026-10-01",
		"concepto": "Reparación de cañería propia", "importe": "1500"})
	ok("cargo particular", code, http.StatusCreated, m)
	code, m = e.a.enviar(http.MethodPost, C+"/cargos", map[string]any{"unidad_id": u["2"], "periodo": "2026-10-01",
		"concepto": "Bonificación por trabajo", "importe": "-500"})
	ok("bonificación", code, http.StatusCreated, m)
	code, m = e.a.enviar(http.MethodPost, A+"/unidades/"+u["1"]+"/deuda-inicial", map[string]any{
		"periodo": "2026-09-01", "importe": "10000", "vencimiento": "2026-09-10"})
	ok("deuda inicial", code, http.StatusCreated, m)

	unidadDe := func(det map[string]any, codigo string) map[string]any {
		t.Helper()
		calc, _ := det["calculo"].(map[string]any)
		res, _ := calc["resultado"].(map[string]any)
		lista, _ := res["unidades"].([]any)
		for _, x := range lista {
			if um := x.(map[string]any); um["codigo"] == codigo {
				return um
			}
		}
		t.Fatalf("no está la unidad %s en %v", codigo, det)
		return nil
	}
	tieneInteres := func(um map[string]any) bool {
		for _, l := range um["lineas"].([]any) {
			if l.(map[string]any)["concepto"] == "interes_deuda" {
				return true
			}
		}
		return false
	}

	code, det := e.a.enviar(http.MethodPost, L+oct+"/calcular", map[string]any{"fecha_calculo": "2026-10-01"})
	ok("calcular oct", code, http.StatusOK, det)
	t.Run("cálculo de octubre", func(t *testing.T) {
		igual("estado", det["liquidacion"].(map[string]any)["estado"], "calculada")
		igual("total de cargos", det["calculo"].(map[string]any)["total_cargos"], "133001")
		// GENERAL 100000 (mayor resto: 1 centavo a la UF 1), Ascensor 20001, extraordinario 9000,
		// fondo 3000 (2 centavos a las UF 2 y 3), cargo +1500 UF 3, bonificación −500 UF 2.
		igual("UF 1 cargos", unidadDe(det, "1")["cargos"], "47333.84")
		igual("UF 2 cargos", unidadDe(det, "2")["cargos"], "46833.83")
		igual("UF 3 cargos", unidadDe(det, "3")["cargos"], "38833.33")
		igual("UF 1 total (con deuda inicial)", unidadDe(det, "1")["total"], "57333.84")
		if tieneInteres(unidadDe(det, "1")) {
			t.Error("la deuda inicial no genera interés el primer mes")
		}
	})

	t.Run("condonar vuelve a borrador", func(t *testing.T) {
		code, d := e.a.enviar(http.MethodPost, L+oct+"/condonaciones", map[string]any{"unidad_id": u["1"], "motivo": "Acuerdo de pago"})
		esperar(t, "condonar", code, http.StatusOK, d)
		igual("estado tras condonar", d["liquidacion"].(map[string]any)["estado"], "borrador")
		code, _ = e.a.enviar(http.MethodPost, L+oct+"/aprobar", nil)
		esperar(t, "no se aprueba un borrador", code, http.StatusConflict)
		code, d = e.a.enviar(http.MethodDelete, L+oct+"/condonaciones/"+u["1"], nil)
		esperar(t, "quitar condonación", code, http.StatusOK, d)
		code, d = e.a.enviar(http.MethodPost, L+oct+"/calcular", map[string]any{"fecha_calculo": "2026-10-01"})
		esperar(t, "recalcular", code, http.StatusOK, d)
		if n := len(d["historial_calculos"].([]any)); n != 2 {
			t.Errorf("historial de cálculos: %d, esperado 2", n)
		}
	})

	code, d := e.a.enviar(http.MethodPost, L+oct+"/aprobar", nil)
	ok("aprobar oct", code, http.StatusOK, d)
	t.Run("aprobada no se toca", func(t *testing.T) {
		code, _ := e.a.enviar(http.MethodPost, C+"/gastos", map[string]any{"periodo": "2026-09-01", "grupo_id": general,
			"concepto": "Tarde", "importe": "1"})
		esperar(t, "gasto en período aprobado", code, http.StatusConflict)
		code, _ = e.a.enviar(http.MethodPost, L+oct+"/calcular", nil)
		esperar(t, "recalcular aprobada", code, http.StatusConflict)
		code, _ = e.a.enviar(http.MethodPost, C+"/tasas-mora", map[string]any{"vigente_desde": "2026-10-01",
			"tasa_mensual": "0.05", "fundamento": "x"})
		esperar(t, "tasa con vigencia en período cerrado", code, http.StatusConflict)
	})
	code, d = e.a.enviar(http.MethodPost, L+oct+"/emitir", nil)
	ok("emitir oct", code, http.StatusOK, d)
	igual("vencimiento", d["liquidacion"].(map[string]any)["vencimiento"], "2026-10-10")

	cuenta := func(cod string) map[string]any {
		t.Helper()
		code, m := e.a.enviar(http.MethodGet, A+"/unidades/"+u[cod]+"/cuenta", nil)
		return ok("cuenta UF "+cod, code, http.StatusOK, m)
	}
	t.Run("cuenta corriente tras emitir", func(t *testing.T) {
		igual("UF 1 deuda", cuenta("1")["deuda"], "57333.84")
		c2 := cuenta("2")
		igual("UF 2 deuda (la bonificación ya se aplicó)", c2["deuda"], "46833.83")
		igual("UF 2 saldo a favor", c2["saldo_a_favor"], "0")
		igual("UF 3 deuda", cuenta("3")["deuda"], "38833.33")
	})

	t.Run("pagos", func(t *testing.T) {
		code, p := e.a.enviar(http.MethodPost, C+"/pagos", map[string]any{"unidad_id": u["1"], "fecha": "2026-10-05",
			"importe": "20000", "referencia": "TRF-001"})
		esperar(t, "pago UF 1", code, http.StatusCreated, p)
		igual("UF 1 saldo a favor del pago", p["saldo_a_favor"], "0")
		igual("UF 1 deuda tras pagar", cuenta("1")["deuda"], "37333.84")
		code, _ = e.a.enviar(http.MethodPost, C+"/pagos", map[string]any{"unidad_id": u["2"], "fecha": "2026-10-05",
			"importe": "1", "referencia": "TRF-001"})
		esperar(t, "referencia repetida", code, http.StatusConflict)
		code, p = e.a.enviar(http.MethodPost, C+"/pagos", map[string]any{"unidad_id": u["3"], "fecha": "2026-10-06",
			"importe": "40000", "referencia": "TRF-002"})
		esperar(t, "pago de más UF 3", code, http.StatusCreated, p)
		igual("UF 3 saldo a favor", p["saldo_a_favor"], "1166.67")
		code, _ = e.a.enviar(http.MethodPost, C+"/pagos", map[string]any{"unidad_id": u["3"], "fecha": "2999-01-01",
			"importe": "1", "referencia": "TRF-FUT"})
		esperar(t, "pago con fecha futura", code, http.StatusBadRequest)
	})

	// ── Noviembre: interés simple sobre el capital vencido al 15/11 ──
	code, m = e.a.enviar(http.MethodPost, C+"/gastos", map[string]any{"periodo": "2026-10-01", "grupo_id": general,
		"concepto": "Sueldos", "importe": "60000"})
	ok("gasto oct", code, http.StatusCreated, m)
	code, liq = e.a.enviar(http.MethodPost, C+"/liquidaciones", map[string]any{"periodo": "2026-11-01"})
	nov := ok("crear nov", code, http.StatusCreated, liq)["id"].(string)
	code, det = e.a.enviar(http.MethodPost, L+nov+"/calcular", map[string]any{"fecha_calculo": "2026-11-15"})
	ok("calcular nov", code, http.StatusOK, det)
	t.Run("cálculo de noviembre", func(t *testing.T) {
		// UF 1: 37333.84 × 3 % = 1120.02; UF 2: 46833.83 × 3 % = 1405.01; UF 3 tiene saldo a favor.
		igual("UF 1 cargos", unidadDe(det, "1")["cargos"], "22120.02")
		igual("UF 2 cargos", unidadDe(det, "2")["cargos"], "22405.01")
		igual("UF 3 cargos", unidadDe(det, "3")["cargos"], "21000")
		igual("UF 3 total (descuenta el saldo a favor)", unidadDe(det, "3")["total"], "19833.33")
	})

	t.Run("reabrir", func(t *testing.T) {
		code, _ := e.c.enviar(http.MethodPost, L+oct+"/reabrir", map[string]any{"motivo": "x"})
		esperar(t, "consulta no reabre", code, http.StatusForbidden)
		code, _ = e.a.enviar(http.MethodPost, L+oct+"/reabrir", nil)
		esperar(t, "reabrir sin motivo", code, http.StatusBadRequest)
		code, m := e.a.enviar(http.MethodPost, L+oct+"/reabrir", map[string]any{"motivo": "Error en sueldos"})
		esperar(t, "reabrir con pagos imputados", code, http.StatusConflict, m)

		_, cuenta1 := e.a.enviar(http.MethodGet, A+"/unidades/"+u["1"]+"/cuenta", nil)
		_, cuenta3 := e.a.enviar(http.MethodGet, A+"/unidades/"+u["3"]+"/cuenta", nil)
		for _, c := range []map[string]any{cuenta1, cuenta3} {
			for _, p := range c["pagos"].([]any) {
				pid := p.(map[string]any)["id"].(string)
				code, m := e.a.enviar(http.MethodPost, A+"/pagos/"+pid+"/anular", map[string]any{"motivo": "Cargado por error"})
				esperar(t, "anular pago", code, http.StatusOK, m)
			}
		}
		igual("UF 1 deuda tras anular el pago", cuenta("1")["deuda"], "57333.84")

		code, m = e.a.enviar(http.MethodPost, L+nov+"/aprobar", nil)
		esperar(t, "aprobar nov con oct emitida (sí se puede)", code, http.StatusOK, m)
		code, m = e.a.enviar(http.MethodPost, L+oct+"/reabrir", map[string]any{"motivo": "Error en sueldos"})
		esperar(t, "reabrir con la siguiente aprobada", code, http.StatusConflict, m)
		code, m = e.a.enviar(http.MethodPost, L+nov+"/reabrir", map[string]any{"motivo": "Hay que reabrir octubre"})
		esperar(t, "reabrir nov aprobada", code, http.StatusOK, m)

		code, m = e.a.enviar(http.MethodPost, L+oct+"/reabrir", map[string]any{"motivo": "Error en sueldos"})
		esperar(t, "reabrir oct", code, http.StatusOK, m)
		igual("estado tras reabrir", m["liquidacion"].(map[string]any)["estado"], "calculada")
		igual("UF 1 deuda tras reabrir (solo la deuda inicial)", cuenta("1")["deuda"], "10000")
		c2 := cuenta("2")
		igual("UF 2 deuda tras reabrir", c2["deuda"], "0")
		igual("UF 2 sin saldo a favor (el ajuste se anuló)", c2["saldo_a_favor"], "0")

		code, _ = e.a.enviar(http.MethodPost, L+nov+"/calcular", nil)
		esperar(t, "nov se recalcula", code, http.StatusOK)
		code, m = e.a.enviar(http.MethodPost, L+nov+"/aprobar", nil)
		esperar(t, "aprobar nov con oct sin emitir", code, http.StatusConflict, m)

		code, m = e.a.enviar(http.MethodPost, L+oct+"/aprobar", nil)
		esperar(t, "volver a aprobar oct", code, http.StatusOK, m)
		code, m = e.a.enviar(http.MethodPost, L+oct+"/emitir", nil)
		esperar(t, "volver a emitir oct", code, http.StatusOK, m)
		igual("UF 2 deuda tras reemitir", cuenta("2")["deuda"], "46833.83")
	})

	t.Run("aislamiento", func(t *testing.T) {
		code, _ := e.b.enviar(http.MethodGet, B+"/liquidaciones/"+oct, nil)
		esperar(t, "B ve una liquidación de A", code, http.StatusNotFound)
		code, _ = e.b.enviar(http.MethodGet, A+"/liquidaciones/"+oct, nil)
		esperar(t, "B entra a la administración A", code, http.StatusNotFound)
		code, _ = e.b.enviar(http.MethodPost, B+"/consorcios/"+cid+"/pagos", map[string]any{"unidad_id": u["1"],
			"fecha": "2026-10-05", "importe": "1", "referencia": "INTRUSO"})
		esperar(t, "B carga un pago en un consorcio de A", code, http.StatusNotFound)
		code, _ = e.b.enviar(http.MethodGet, B+"/unidades/"+u["1"]+"/cuenta", nil)
		esperar(t, "B ve la cuenta de una unidad de A", code, http.StatusNotFound)
		code, _ = e.b.enviar(http.MethodPost, B+"/liquidaciones/"+oct+"/reabrir", map[string]any{"motivo": "x"})
		esperar(t, "B reabre una liquidación de A", code, http.StatusNotFound)
	})
}
