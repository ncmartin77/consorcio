// Package expensas es el motor de liquidación: código puro, sin base de datos ni HTTP.
// Recibe todo lo necesario (gastos, coeficientes, deudas, tasas y fechas) y devuelve
// los cargos de cada unidad. Mismas entradas → mismos resultados, siempre.
//
// Reglas (docs/decisiones-liquidaciones.md):
//   - Prorrateo por grupo con los coeficientes vigentes; centavos repartidos por
//     mayor resto (desempate por código de unidad): la suma da exacto el total.
//   - Interés simple (CCyC 770): tasa mensual × capital impago a la fecha de cierre
//     (deuda anterior menos intereses impagos). Nunca sobre intereses.
//     La deuda inicial migrada no genera interés el primer mes.
//   - Sin mora del mes: el atraso se cobra como interés en la liquidación siguiente
//     (como el sistema actual desde la v9.0).
//   - Condonación (el switch "sin interés" de cada unidad al cerrar): sin interés.
//   - Gastos extraordinarios a cobrar: se prorratean igual pero van en una línea
//     aparte. Los pagados con el fondo de reserva no llegan al motor.
//   - Saldo anterior con signo: positivo es deuda, negativo es saldo a favor.
package expensas

import (
	"errors"
	"fmt"
	"sort"

	"github.com/google/uuid"
	"github.com/shopspring/decimal"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/fecha"
)

var (
	cien    = decimal.NewFromInt(100)
	centavo = decimal.New(1, -2)
)

// Concepto de cada línea de la liquidación de una unidad.
type Concepto string

const (
	SaldoAnterior  Concepto = "saldo_anterior" // informativo: ya está en la cuenta corriente
	Expensas       Concepto = "expensas"       // gastos del grupo prorrateados
	FondoReserva   Concepto = "fondo_reserva"
	Particular     Concepto = "particular" // cargo a una sola unidad
	InteresDeuda   Concepto = "interes_deuda"
	Extraordinaria Concepto = "extraordinaria" // gastos extraordinarios a cobrar, prorrateados
)

type Unidad struct {
	ID     uuid.UUID
	Codigo string
}

type Grupo struct {
	ID           uuid.UUID
	Nombre       string
	Coeficientes map[uuid.UUID]decimal.Decimal // unidad → porcentaje (suma 100)
}

type Gasto struct {
	ID             uuid.UUID
	GrupoID        uuid.UUID
	Concepto       string
	Importe        decimal.Decimal
	Extraordinario bool // naturaleza extraordinaria y se cobra con las expensas
}

type CargoParticular struct {
	UnidadID uuid.UUID
	Concepto string
	Importe  decimal.Decimal
}

// Situacion de la unidad al momento de liquidar, sacada de la cuenta corriente.
type Situacion struct {
	SaldoAnterior  decimal.Decimal // con signo: >0 debe, <0 saldo a favor
	CapitalVencido decimal.Decimal // capital impago a la fecha de cierre: base del interés
	DeudaInicial   bool            // la deuda viene de la migración y es el primer mes
	Condonada      bool            // sin interés en esta liquidación
}

type Entrada struct {
	Unidades     []Unidad // activas
	Grupos       map[uuid.UUID]Grupo
	Gastos       []Gasto
	FondoReserva decimal.Decimal // monto mensual (0 = no hay)
	GrupoFondo   uuid.UUID       // grupo con el que se reparte el fondo
	Particulares []CargoParticular
	Situaciones  map[uuid.UUID]Situacion
	TasaMensual  decimal.Decimal // 0.05 = 5 %; la vigente el día 1 del mes de la liquidación
	FechaCalculo fecha.Fecha     // fecha de cierre: queda guardada con la liquidación
}

type Linea struct {
	Concepto Concepto        `json:"concepto"`
	Detalle  string          `json:"detalle"`
	GrupoID  *uuid.UUID      `json:"grupo_id,omitempty"`
	Importe  decimal.Decimal `json:"importe"`
}

type ResultadoUnidad struct {
	UnidadID uuid.UUID       `json:"unidad_id"`
	Codigo   string          `json:"codigo"`
	Lineas   []Linea         `json:"lineas"`
	Cargos   decimal.Decimal `json:"cargos"` // nuevo en este período (todo menos saldo anterior)
	Total    decimal.Decimal `json:"total"`  // saldo anterior + cargos
}

type Resultado struct {
	Unidades            []ResultadoUnidad             `json:"unidades"`
	TotalPorGrupo       map[uuid.UUID]decimal.Decimal `json:"total_por_grupo"` // ordinarios
	TotalExtraordinario map[uuid.UUID]decimal.Decimal `json:"total_extraordinario"`
	TotalCargos         decimal.Decimal               `json:"total_cargos"`
}

// Redondear: half-up a centavos.
func Redondear(d decimal.Decimal) decimal.Decimal { return d.Round(2) }

// Prorratear reparte total entre las unidades según sus porcentajes, en centavos
// exactos: primero el piso de cada parte y después un centavo a las de mayor resto
// (desempate por código). La suma de las partes es exactamente total.
func Prorratear(total decimal.Decimal, coef map[uuid.UUID]decimal.Decimal, codigos map[uuid.UUID]string) (map[uuid.UUID]decimal.Decimal, error) {
	suma := decimal.Zero
	for _, p := range coef {
		suma = suma.Add(p)
	}
	if !suma.Equal(cien) {
		return nil, fmt.Errorf("los coeficientes suman %s %%, no 100 %%", suma)
	}
	if !total.Equal(total.Round(2)) {
		return nil, fmt.Errorf("el total %s tiene más de 2 decimales", total)
	}
	negativo := total.IsNegative()
	abs := total.Abs()

	type parte struct {
		id     uuid.UUID
		piso   decimal.Decimal
		resto  decimal.Decimal
		codigo string
	}
	partes := make([]parte, 0, len(coef))
	asignado := decimal.Zero
	for id, p := range coef {
		exacto := abs.Mul(p).Div(cien) // decimal: sin pérdida para porcentajes de 6 decimales
		piso := exacto.Truncate(2)
		partes = append(partes, parte{id: id, piso: piso, resto: exacto.Sub(piso), codigo: codigos[id]})
		asignado = asignado.Add(piso)
	}
	sort.Slice(partes, func(i, j int) bool {
		if c := partes[i].resto.Cmp(partes[j].resto); c != 0 {
			return c > 0
		}
		return partes[i].codigo < partes[j].codigo
	})
	faltan := abs.Sub(asignado).Div(centavo).IntPart() // centavos sin asignar (< cantidad de unidades)
	out := make(map[uuid.UUID]decimal.Decimal, len(partes))
	for i, p := range partes {
		v := p.piso
		if int64(i) < faltan {
			v = v.Add(centavo)
		}
		if negativo {
			v = v.Neg()
		}
		out[p.id] = v
	}
	return out, nil
}

// Calcular liquida un período.
func Calcular(e Entrada) (Resultado, error) {
	if len(e.Unidades) == 0 {
		return Resultado{}, errors.New("el consorcio no tiene unidades activas")
	}
	if e.FechaCalculo.EsCero() {
		return Resultado{}, errors.New("falta la fecha de cálculo")
	}
	if e.TasaMensual.IsNegative() {
		return Resultado{}, errors.New("tasa de mora negativa")
	}
	activas := map[uuid.UUID]string{}
	for _, u := range e.Unidades {
		activas[u.ID] = u.Codigo
	}

	// Total a repartir por grupo: ordinarios y extraordinarios por separado.
	totales := map[uuid.UUID]decimal.Decimal{}
	extraord := map[uuid.UUID]decimal.Decimal{}
	for _, g := range e.Gastos {
		if _, ok := e.Grupos[g.GrupoID]; !ok {
			return Resultado{}, fmt.Errorf("el gasto %q usa un grupo sin coeficientes vigentes", g.Concepto)
		}
		if g.Extraordinario {
			extraord[g.GrupoID] = extraord[g.GrupoID].Add(g.Importe)
		} else {
			totales[g.GrupoID] = totales[g.GrupoID].Add(g.Importe)
		}
	}
	if e.FondoReserva.IsPositive() {
		if _, ok := e.Grupos[e.GrupoFondo]; !ok {
			return Resultado{}, errors.New("el fondo de reserva usa un grupo sin coeficientes vigentes")
		}
	}

	lineas := map[uuid.UUID][]Linea{}
	repartir := func(grupoID uuid.UUID, total decimal.Decimal, concepto Concepto, detalle string) error {
		g := e.Grupos[grupoID]
		for uid := range g.Coeficientes {
			if _, ok := activas[uid]; !ok {
				return fmt.Errorf("el grupo %s tiene coeficiente para una unidad inactiva o de otro consorcio", g.Nombre)
			}
		}
		partes, err := Prorratear(total, g.Coeficientes, activas)
		if err != nil {
			return fmt.Errorf("grupo %s: %w", g.Nombre, err)
		}
		gid := grupoID
		for uid, imp := range partes {
			lineas[uid] = append(lineas[uid], Linea{Concepto: concepto, Detalle: detalle, GrupoID: &gid, Importe: imp})
		}
		return nil
	}
	porNombre := func(m map[uuid.UUID]decimal.Decimal) []uuid.UUID {
		ids := make([]uuid.UUID, 0, len(m))
		for id := range m {
			ids = append(ids, id)
		}
		sort.Slice(ids, func(i, j int) bool { return e.Grupos[ids[i]].Nombre < e.Grupos[ids[j]].Nombre })
		return ids
	}
	for _, gid := range porNombre(totales) {
		if err := repartir(gid, totales[gid], Expensas, "Expensas "+e.Grupos[gid].Nombre); err != nil {
			return Resultado{}, err
		}
	}
	for _, gid := range porNombre(extraord) {
		if err := repartir(gid, extraord[gid], Extraordinaria, "Gastos extraordinarios "+e.Grupos[gid].Nombre); err != nil {
			return Resultado{}, err
		}
	}
	if e.FondoReserva.IsPositive() {
		if err := repartir(e.GrupoFondo, e.FondoReserva, FondoReserva, "Fondo de reserva"); err != nil {
			return Resultado{}, err
		}
	}
	for _, p := range e.Particulares {
		if _, ok := activas[p.UnidadID]; !ok {
			return Resultado{}, fmt.Errorf("cargo particular %q para una unidad inactiva o inexistente", p.Concepto)
		}
		lineas[p.UnidadID] = append(lineas[p.UnidadID], Linea{Concepto: Particular, Detalle: p.Concepto, Importe: Redondear(p.Importe)})
	}

	res := Resultado{TotalPorGrupo: totales, TotalExtraordinario: extraord, TotalCargos: decimal.Zero}
	for _, u := range e.Unidades {
		s := e.Situaciones[u.ID]
		ls := lineas[u.ID]

		if !s.Condonada && !s.DeudaInicial && s.CapitalVencido.IsPositive() {
			if i := Redondear(s.CapitalVencido.Mul(e.TasaMensual)); i.IsPositive() {
				ls = append(ls, Linea{Concepto: InteresDeuda, Detalle: "Interés sobre deuda vencida", Importe: i})
			}
		}

		cargos := decimal.Zero
		for _, l := range ls {
			cargos = cargos.Add(l.Importe)
		}
		todas := ls
		if !s.SaldoAnterior.IsZero() {
			todas = append([]Linea{{Concepto: SaldoAnterior, Detalle: "Saldo anterior", Importe: s.SaldoAnterior}}, ls...)
		}
		res.Unidades = append(res.Unidades, ResultadoUnidad{
			UnidadID: u.ID, Codigo: u.Codigo, Lineas: todas, Cargos: cargos, Total: s.SaldoAnterior.Add(cargos),
		})
		res.TotalCargos = res.TotalCargos.Add(cargos)
	}
	sort.Slice(res.Unidades, func(i, j int) bool { return menorCodigo(res.Unidades[i].Codigo, res.Unidades[j].Codigo) })
	return res, nil
}

// Orden "natural" de códigos: por largo y después alfabético ("2" antes que "10").
func menorCodigo(a, b string) bool {
	if len(a) != len(b) {
		return len(a) < len(b)
	}
	return a < b
}
