package expensas

import (
	"testing"

	"github.com/google/uuid"
	"github.com/shopspring/decimal"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/fecha"
)

func d(s string) decimal.Decimal { return decimal.RequireFromString(s) }

type casa struct {
	unidades []Unidad
	ids      []uuid.UUID
	grupo    Grupo
}

// nuevaCasa arma n unidades con códigos "1".."n" y un grupo GENERAL con los porcentajes dados.
func nuevaCasa(porcentajes ...string) casa {
	c := casa{grupo: Grupo{ID: uuid.New(), Nombre: "GENERAL", Coeficientes: map[uuid.UUID]decimal.Decimal{}}}
	for i, p := range porcentajes {
		id := uuid.New()
		c.ids = append(c.ids, id)
		c.unidades = append(c.unidades, Unidad{ID: id, Codigo: string(rune('1' + i))})
		c.grupo.Coeficientes[id] = d(p)
	}
	return c
}

func (c casa) entrada(gastos ...string) Entrada {
	e := Entrada{
		Unidades:     c.unidades,
		Grupos:       map[uuid.UUID]Grupo{c.grupo.ID: c.grupo},
		Situaciones:  map[uuid.UUID]Situacion{},
		TasaMensual:  d("0.05"),
		FechaCalculo: fecha.Nueva(2026, 11, 1),
	}
	for _, g := range gastos {
		e.Gastos = append(e.Gastos, Gasto{ID: uuid.New(), GrupoID: c.grupo.ID, Concepto: "gasto", Importe: d(g)})
	}
	return e
}

func linea(r ResultadoUnidad, c Concepto) decimal.Decimal {
	t := decimal.Zero
	for _, l := range r.Lineas {
		if l.Concepto == c {
			t = t.Add(l.Importe)
		}
	}
	return t
}

func porID(res Resultado, id uuid.UUID) ResultadoUnidad {
	for _, u := range res.Unidades {
		if u.UnidadID == id {
			return u
		}
	}
	return ResultadoUnidad{}
}

func igual(t *testing.T, que string, obtenido decimal.Decimal, esperado string) {
	t.Helper()
	if !obtenido.Equal(d(esperado)) {
		t.Errorf("%s: %s, esperado %s", que, obtenido, esperado)
	}
}

// Ejemplo del documento v0.1: 1.000.000 con 15/20/25/40 %.
func TestEjemploDelDocumento(t *testing.T) {
	c := nuevaCasa("15", "20", "25", "40")
	res, err := Calcular(c.entrada("1000000"))
	if err != nil {
		t.Fatal(err)
	}
	for i, esp := range []string{"150000", "200000", "250000", "400000"} {
		igual(t, "unidad "+c.unidades[i].Codigo, linea(porID(res, c.ids[i]), Expensas), esp)
	}
	igual(t, "total de cargos", res.TotalCargos, "1000000")
}

func TestRedondeoPorMayorResto(t *testing.T) {
	t.Run("100 pesos en tercios", func(t *testing.T) {
		c := nuevaCasa("33.333334", "33.333333", "33.333333")
		res, _ := Calcular(c.entrada("100"))
		// exactos: 33.333334 / 33.333333 / 33.333333 → pisos 33.33 c/u, sobra 1 centavo:
		// va al de mayor resto (la unidad 1).
		igual(t, "u1", linea(porID(res, c.ids[0]), Expensas), "33.34")
		igual(t, "u2", linea(porID(res, c.ids[1]), Expensas), "33.33")
		igual(t, "u3", linea(porID(res, c.ids[2]), Expensas), "33.33")
	})
	t.Run("empate de restos: decide el código", func(t *testing.T) {
		c := nuevaCasa("50", "50")
		res, _ := Calcular(c.entrada("0.01"))
		igual(t, "u1 se lleva el centavo", linea(porID(res, c.ids[0]), Expensas), "0.01")
		igual(t, "u2", linea(porID(res, c.ids[1]), Expensas), "0")
	})
	t.Run("la suma siempre da exacto", func(t *testing.T) {
		c := nuevaCasa("7.721", "2.064", "2.064", "2.064", "6.214", "79.873")
		for _, total := range []string{"453781.74", "230331.24", "0.07", "1", "999999.99"} {
			res, err := Calcular(c.entrada(total))
			if err != nil {
				t.Fatal(err)
			}
			suma := decimal.Zero
			for _, u := range res.Unidades {
				suma = suma.Add(linea(u, Expensas))
			}
			igual(t, "suma de "+total, suma, total)
		}
	})
	t.Run("nota de crédito (gasto negativo)", func(t *testing.T) {
		c := nuevaCasa("33.333334", "33.333333", "33.333333")
		res, _ := Calcular(c.entrada("-100"))
		igual(t, "u1", linea(porID(res, c.ids[0]), Expensas), "-33.34")
		igual(t, "total", res.TotalCargos, "-100")
	})
}

func TestVariosGruposYFondo(t *testing.T) {
	c := nuevaCasa("40", "60")
	ascensor := Grupo{ID: uuid.New(), Nombre: "ASCENSOR", Coeficientes: map[uuid.UUID]decimal.Decimal{c.ids[1]: d("100")}}
	e := c.entrada("1000")
	e.Grupos[ascensor.ID] = ascensor
	e.Gastos = append(e.Gastos, Gasto{ID: uuid.New(), GrupoID: ascensor.ID, Concepto: "abono ascensor", Importe: d("300")})
	e.FondoReserva, e.GrupoFondo = d("200"), c.grupo.ID
	e.Particulares = []CargoParticular{{UnidadID: c.ids[0], Concepto: "reparación balcón", Importe: d("55.5")}}
	res, err := Calcular(e)
	if err != nil {
		t.Fatal(err)
	}
	u1, u2 := porID(res, c.ids[0]), porID(res, c.ids[1])
	igual(t, "u1 expensas (solo GENERAL)", linea(u1, Expensas), "400")
	igual(t, "u2 expensas (GENERAL + ascensor)", linea(u2, Expensas), "900")
	igual(t, "u1 fondo", linea(u1, FondoReserva), "80")
	igual(t, "u2 fondo", linea(u2, FondoReserva), "120")
	igual(t, "u1 particular", linea(u1, Particular), "55.50")
	igual(t, "u2 particular", linea(u2, Particular), "0")
	igual(t, "total de cargos", res.TotalCargos, "1555.5")
}

func TestInteresSimple(t *testing.T) {
	c := nuevaCasa("50", "50")
	e := c.entrada("1000")
	e.Situaciones[c.ids[0]] = Situacion{SaldoAnterior: d("10600"), CapitalVencido: d("10000")} // 600 de intereses viejos
	res, _ := Calcular(e)
	u := porID(res, c.ids[0])
	// Simple: 5 % de 10.000 de capital = 500. Compuesto (v9.x, o v10 con "capitalizar") daría 530.
	igual(t, "interés sobre el capital", linea(u, InteresDeuda), "500")
	igual(t, "total = saldo + expensas + interés", u.Total, "11600")
	igual(t, "cargos nuevos", u.Cargos, "1000")

	t.Run("deuda inicial migrada: sin interés el primer mes", func(t *testing.T) {
		e.Situaciones[c.ids[0]] = Situacion{SaldoAnterior: d("10000"), CapitalVencido: d("10000"), DeudaInicial: true}
		res, _ := Calcular(e)
		igual(t, "interés", linea(porID(res, c.ids[0]), InteresDeuda), "0")
	})
	t.Run("condonada: sin interés", func(t *testing.T) {
		e.Situaciones[c.ids[0]] = Situacion{SaldoAnterior: d("10000"), CapitalVencido: d("10000"), Condonada: true}
		res, _ := Calcular(e)
		igual(t, "interés", linea(porID(res, c.ids[0]), InteresDeuda), "0")
	})
	t.Run("redondeo del interés half-up", func(t *testing.T) {
		e.Situaciones[c.ids[0]] = Situacion{SaldoAnterior: d("0.1"), CapitalVencido: d("0.1")} // 0.005 → 0.01
		res, _ := Calcular(e)
		igual(t, "interés", linea(porID(res, c.ids[0]), InteresDeuda), "0.01")
	})
}

func TestSinMoraDelMes(t *testing.T) {
	// Desde la v9.0 del sistema actual no hay recargo dentro de la misma liquidación:
	// aunque se cierre después del vencimiento y sin pagos, solo hay expensas.
	c := nuevaCasa("50", "50")
	e := c.entrada("1000")
	e.FechaCalculo = fecha.Nueva(2026, 12, 20)
	res, _ := Calcular(e)
	u := porID(res, c.ids[0])
	igual(t, "cargos sin deuda anterior", u.Cargos, "500")
	if len(u.Lineas) != 1 {
		t.Errorf("líneas de más: %+v", u.Lineas)
	}
}

func TestExtraordinariosEnLineaAparte(t *testing.T) {
	c := nuevaCasa("40", "60")
	e := c.entrada("1000")
	e.Gastos = append(e.Gastos, Gasto{ID: uuid.New(), GrupoID: c.grupo.ID, Concepto: "impermeabilización", Importe: d("5000"), Extraordinario: true})
	res, err := Calcular(e)
	if err != nil {
		t.Fatal(err)
	}
	u1 := porID(res, c.ids[0])
	igual(t, "ordinarias u1", linea(u1, Expensas), "400")
	igual(t, "extraordinarias u1", linea(u1, Extraordinaria), "2000")
	igual(t, "total ordinario del grupo", res.TotalPorGrupo[c.grupo.ID], "1000")
	igual(t, "total extraordinario del grupo", res.TotalExtraordinario[c.grupo.ID], "5000")
	igual(t, "total de cargos", res.TotalCargos, "6000")
}

func TestSaldoAFavor(t *testing.T) {
	c := nuevaCasa("50", "50")
	e := c.entrada("1000")
	e.Situaciones[c.ids[0]] = Situacion{SaldoAnterior: d("-200")}
	res, _ := Calcular(e)
	u := porID(res, c.ids[0])
	igual(t, "total descuenta el saldo a favor", u.Total, "300")
	igual(t, "interés sobre saldo a favor", linea(u, InteresDeuda), "0")
}

func TestErroresDeEntrada(t *testing.T) {
	c := nuevaCasa("60", "40.001") // suma 100,001 como Edificio Brasil
	if _, err := Calcular(c.entrada("100")); err == nil {
		t.Error("aceptó coeficientes que suman 100,001 %")
	}
	c = nuevaCasa("60", "40")
	e := c.entrada("100")
	e.Gastos[0].GrupoID = uuid.New()
	if _, err := Calcular(e); err == nil {
		t.Error("aceptó un gasto con grupo sin coeficientes")
	}
	e = c.entrada("100.005")
	if _, err := Calcular(e); err == nil {
		t.Error("aceptó un gasto con más de 2 decimales")
	}
	e = c.entrada("100")
	e.Unidades = e.Unidades[:1] // la unidad 2 quedó inactiva pero tiene coeficiente
	if _, err := Calcular(e); err == nil {
		t.Error("aceptó coeficiente de una unidad inactiva")
	}
}

func TestImputacion(t *testing.T) {
	oct, nov := fecha.Nueva(2026, 10, 1), fecha.Nueva(2026, 11, 1)
	capOct, intOct := Partida{ID: uuid.New(), Periodo: oct, Pendiente: d("1000")}, Partida{ID: uuid.New(), EsInteres: true, Periodo: oct, Pendiente: d("50")}
	capNov, intNov := Partida{ID: uuid.New(), Periodo: nov, Pendiente: d("1000")}, Partida{ID: uuid.New(), EsInteres: true, Periodo: nov, Pendiente: d("30")}
	partidas := []Partida{capNov, capOct, intNov, intOct} // desordenadas a propósito

	aps, sobra := Imputar(d("1100"), partidas)
	esperado := []struct {
		id  uuid.UUID
		imp string
	}{{intOct.ID, "50"}, {intNov.ID, "30"}, {capOct.ID, "1000"}, {capNov.ID, "20"}}
	if len(aps) != len(esperado) {
		t.Fatalf("aplicaciones: %+v", aps)
	}
	for i, e := range esperado {
		if aps[i].PartidaID != e.id || !aps[i].Importe.Equal(d(e.imp)) {
			t.Errorf("aplicación %d: %+v, esperado %s", i, aps[i], e.imp)
		}
	}
	igual(t, "sobrante", sobra, "0")

	_, sobra = Imputar(d("2500"), partidas)
	igual(t, "pago de más queda a favor", sobra, "420")
}
