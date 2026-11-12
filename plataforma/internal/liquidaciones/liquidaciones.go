// Package liquidaciones: parámetros, tasas de mora, gastos, cargos particulares y el ciclo
// de vida de una liquidación (borrador → calculada → aprobada → emitida, y reabrir).
//
// La liquidación del período P reparte los gastos de P−1 (mes vencido) con los
// coeficientes vigentes al último día de P−1, y suma los cargos particulares de P, el fondo
// de reserva y el interés por deuda. El cálculo lo hace el motor puro (internal/expensas);
// acá se juntan las entradas, se guarda cada cálculo y, al emitir, sus líneas pasan a la
// cuenta corriente de cada unidad.
package liquidaciones

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shopspring/decimal"

	"github.com/ncmartin77/consorcio/plataforma/internal/cuentas"
	"github.com/ncmartin77/consorcio/plataforma/internal/expensas"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/api"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/fecha"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/httpx"
)

type Servicio struct{ pool *pgxpool.Pool }

func NuevoServicio(pool *pgxpool.Pool) *Servicio { return &Servicio{pool: pool} }

// ── Entradas de la API ───────────────────────────────────────────────────────

type altaParametros struct {
	VigenteDesde        fecha.Fecha     `json:"vigente_desde"`
	DiaVencimiento      int16           `json:"dia_vencimiento"`
	FondoReservaMensual decimal.Decimal `json:"fondo_reserva_mensual"`
	GrupoFondoID        *uuid.UUID      `json:"grupo_fondo_id"`
}

type altaTasa struct {
	VigenteDesde fecha.Fecha     `json:"vigente_desde"`
	TasaMensual  decimal.Decimal `json:"tasa_mensual"` // 0.05 = 5 % mensual
	Fundamento   string          `json:"fundamento"`
}

type altaGasto struct {
	Periodo      fecha.Fecha     `json:"periodo"` // mes del gasto (AAAA-MM-01)
	GrupoID      uuid.UUID       `json:"grupo_id"`
	Concepto     string          `json:"concepto"`
	Proveedor    *string         `json:"proveedor"`
	Importe      decimal.Decimal `json:"importe"`
	Naturaleza   string          `json:"naturaleza"`
	Habitualidad string          `json:"habitualidad"`
	Financiacion string          `json:"financiacion"`
	Respaldo     *string         `json:"respaldo"`
}

type altaCargo struct {
	UnidadID uuid.UUID       `json:"unidad_id"`
	Periodo  fecha.Fecha     `json:"periodo"` // período de la liquidación
	Concepto string          `json:"concepto"`
	Importe  decimal.Decimal `json:"importe"`
}

type altaLiquidacion struct {
	Periodo fecha.Fecha `json:"periodo"`
}

type pedidoCalculo struct {
	FechaCalculo *fecha.Fecha `json:"fecha_calculo"` // fecha de cierre; por defecto hoy
}

type altaCondonacion struct {
	UnidadID uuid.UUID `json:"unidad_id"`
	Motivo   string    `json:"motivo"`
}

type conMotivo struct {
	Motivo string `json:"motivo"`
}

// ── Salidas ──────────────────────────────────────────────────────────────────

type Calculo struct {
	ID           uuid.UUID       `json:"id"`
	FechaCalculo fecha.Fecha     `json:"fecha_calculo"`
	TasaMensual  decimal.Decimal `json:"tasa_mensual"`
	TotalCargos  decimal.Decimal `json:"total_cargos"`
	Resultado    json.RawMessage `json:"resultado"`
	CreadoEn     time.Time       `json:"creado_en"`
}

type Detalle struct {
	Liquidacion   dbq.Liquidacion              `json:"liquidacion"`
	Calculo       *Calculo                     `json:"calculo"` // el vigente
	Historial     []dbq.ListarCalculosRow      `json:"historial_calculos"`
	Condonaciones []dbq.LiquidacionCondonacion `json:"condonaciones"`
}

// ── Utilidades ───────────────────────────────────────────────────────────────

func importeValido(d decimal.Decimal, permiteNegativo bool) bool {
	if d.IsZero() || (!permiteNegativo && d.IsNegative()) {
		return false
	}
	return d.Equal(d.Round(2)) && d.Abs().LessThan(decimal.New(1, 12))
}

func texto(p *string) *string {
	if p == nil {
		return nil
	}
	t := strings.TrimSpace(*p)
	if t == "" {
		return nil
	}
	return &t
}

func defecto(v, d string) string {
	if v == "" {
		return d
	}
	return v
}

// periodoAbierto controla que la liquidación del período P se pueda cambiar: si ya está
// aprobada o emitida, no; si estaba calculada, vuelve a borrador (hay que recalcular).
func periodoAbierto(ctx context.Context, q *dbq.Queries, cid uuid.UUID, p fecha.Fecha) error {
	estado, err := q.EstadoLiquidacionPeriodo(ctx, dbq.EstadoLiquidacionPeriodoParams{ConsorcioID: cid, Periodo: p})
	if err != nil {
		return err
	}
	if estado == "aprobada" || estado == "emitida" {
		return api.Conflicto(fmt.Sprintf("la liquidación de %s ya está %s: reabrila para cambiarla", p.String()[:7], estado))
	}
	_, err = q.MarcarDesactualizada(ctx, dbq.MarcarDesactualizadaParams{ConsorcioID: cid, Periodo: p})
	return err
}

// vigenciaLibre: una tasa o parámetro nuevo tiene que regir después del último período
// aprobado o emitido, para no cambiar una liquidación cerrada.
func vigenciaLibre(ctx context.Context, q *dbq.Queries, cid uuid.UUID, desde fecha.Fecha) error {
	ultimo, err := q.UltimoPeriodoCerrado(ctx, cid)
	if err != nil {
		return err
	}
	if !ultimo.EsCero() && !desde.Despues(ultimo) {
		return api.Conflicto(fmt.Sprintf("la liquidación de %s ya está cerrada: la vigencia tiene que empezar después", ultimo.String()[:7]))
	}
	return nil
}

func detalle(ctx context.Context, q *dbq.Queries, l dbq.Liquidacion) (Detalle, error) {
	d := Detalle{Liquidacion: l}
	var err error
	if l.CalculoID != nil {
		c, err := q.ObtenerCalculo(ctx, *l.CalculoID)
		if err != nil {
			return d, err
		}
		d.Calculo = &Calculo{ID: c.ID, FechaCalculo: c.FechaCalculo, TasaMensual: c.TasaMensual,
			TotalCargos: c.TotalCargos, Resultado: c.Resultado, CreadoEn: c.CreadoEn}
	}
	if d.Historial, err = api.Lista(q.ListarCalculos(ctx, l.ID)); err != nil {
		return d, err
	}
	d.Condonaciones, err = api.Lista(q.ListarCondonaciones(ctx, l.ID))
	return d, err
}

// obtenerBloqueada trae la liquidación después de bloquear su consorcio.
func obtenerBloqueada(ctx context.Context, q *dbq.Queries, id uuid.UUID) (dbq.Liquidacion, error) {
	l, err := q.ObtenerLiquidacion(ctx, id)
	if err != nil {
		return l, err
	}
	if _, err := q.BloquearConsorcio(ctx, l.ConsorcioID); err != nil {
		return l, err
	}
	return q.ObtenerLiquidacion(ctx, id) // releída con el bloqueo tomado
}

// ── Cálculo ──────────────────────────────────────────────────────────────────

// armarEntrada junta todo lo que necesita el motor para liquidar el período de l.
func armarEntrada(ctx context.Context, q *dbq.Queries, l dbq.Liquidacion, fc fecha.Fecha) (expensas.Entrada, *uuid.UUID, error) {
	P := l.Periodo
	periodoGastos := P.SumarMeses(-1)
	cierreGastos := P.SumarDias(-1) // coeficientes vigentes al último día del mes de los gastos
	e := expensas.Entrada{
		Grupos: map[uuid.UUID]expensas.Grupo{}, Situaciones: map[uuid.UUID]expensas.Situacion{},
		FechaCalculo: fc,
	}

	par, err := q.ParametrosVigentes(ctx, dbq.ParametrosVigentesParams{ConsorcioID: l.ConsorcioID, Fecha: P})
	if errors.Is(err, pgx.ErrNoRows) {
		return e, nil, api.Conflicto("faltan los parámetros del consorcio (vencimiento y fondo de reserva) vigentes en " + P.String()[:7])
	} else if err != nil {
		return e, nil, err
	}
	tasa, err := q.TasaVigente(ctx, dbq.TasaVigenteParams{ConsorcioID: l.ConsorcioID, Fecha: P})
	if errors.Is(err, pgx.ErrNoRows) {
		return e, nil, api.Conflicto("falta una tasa de mora vigente en " + P.String()[:7] + " (puede ser 0)")
	} else if err != nil {
		return e, nil, err
	}
	e.TasaMensual = tasa.TasaMensual
	e.FondoReserva = par.FondoReservaMensual
	if par.GrupoFondoID != nil {
		e.GrupoFondo = *par.GrupoFondoID
	}

	unidades, err := q.ListarUnidades(ctx, l.ConsorcioID)
	if err != nil {
		return e, nil, err
	}
	for _, u := range unidades {
		if u.Activa {
			e.Unidades = append(e.Unidades, expensas.Unidad{ID: u.ID, Codigo: u.Codigo})
		}
	}

	grupos, err := q.ListarGrupos(ctx, l.ConsorcioID)
	if err != nil {
		return e, nil, err
	}
	for _, g := range grupos {
		cs, err := q.CoeficientesVigentes(ctx, dbq.CoeficientesVigentesParams{GrupoID: g.ID, Fecha: cierreGastos})
		if err != nil {
			return e, nil, err
		}
		if len(cs) == 0 {
			continue
		}
		coef := map[uuid.UUID]decimal.Decimal{}
		for _, c := range cs {
			coef[c.UnidadID] = c.Porcentaje
		}
		e.Grupos[g.ID] = expensas.Grupo{ID: g.ID, Nombre: g.Nombre, Coeficientes: coef}
	}

	gastos, err := q.GastosParaLiquidar(ctx, dbq.GastosParaLiquidarParams{ConsorcioID: l.ConsorcioID, Periodo: periodoGastos})
	if err != nil {
		return e, nil, err
	}
	for _, g := range gastos {
		e.Gastos = append(e.Gastos, expensas.Gasto{ID: g.ID, GrupoID: g.GrupoID, Concepto: g.Concepto,
			Importe: g.Importe, Extraordinario: g.Naturaleza == "extraordinaria"})
	}
	cargos, err := q.CargosParaLiquidar(ctx, dbq.CargosParaLiquidarParams{ConsorcioID: l.ConsorcioID, Periodo: P})
	if err != nil {
		return e, nil, err
	}
	for _, c := range cargos {
		e.Particulares = append(e.Particulares, expensas.CargoParticular{UnidadID: c.UnidadID, Concepto: c.Concepto, Importe: c.Importe})
	}

	// Situación de cada unidad según su cuenta corriente.
	hayEmitidas, err := q.HayEmitidas(ctx, l.ConsorcioID)
	if err != nil {
		return e, nil, err
	}
	pend, err := q.PendientesConsorcio(ctx, l.ConsorcioID)
	if err != nil {
		return e, nil, err
	}
	creditos, err := q.CreditosConsorcio(ctx, l.ConsorcioID)
	if err != nil {
		return e, nil, err
	}
	condonadas, err := q.ListarCondonaciones(ctx, l.ID)
	if err != nil {
		return e, nil, err
	}
	for _, u := range e.Unidades {
		e.Situaciones[u.ID] = expensas.Situacion{SaldoAnterior: decimal.Zero, CapitalVencido: decimal.Zero,
			DeudaInicial: !hayEmitidas}
	}
	for _, p := range pend {
		s, ok := e.Situaciones[p.UnidadID]
		if !ok {
			continue // unidad inactiva
		}
		s.SaldoAnterior = s.SaldoAnterior.Add(p.Pendiente)
		if p.Tipo == "capital" && p.Vencimiento.Antes(fc) {
			s.CapitalVencido = s.CapitalVencido.Add(p.Pendiente)
		}
		e.Situaciones[p.UnidadID] = s
	}
	for _, c := range creditos {
		if s, ok := e.Situaciones[c.UnidadID]; ok {
			s.SaldoAnterior = s.SaldoAnterior.Sub(c.Credito)
			e.Situaciones[c.UnidadID] = s
		}
	}
	for _, c := range condonadas {
		if s, ok := e.Situaciones[c.UnidadID]; ok {
			s.Condonada = true
			e.Situaciones[c.UnidadID] = s
		}
	}
	return e, &tasa.ID, nil
}

// ── Emisión y reapertura ─────────────────────────────────────────────────────

const prefijoAjuste = "liquidacion:"

// emitir pasa las líneas del cálculo vigente a la cuenta corriente: una partida por línea
// positiva (capital o interés). Las líneas negativas (gastos negativos, bonificaciones)
// quedan como un ajuste a favor de la unidad (pago con medio "bonificacion").
func emitir(ctx context.Context, tx api.Tx, l dbq.Liquidacion) (dbq.Liquidacion, error) {
	q := tx.Q
	c, err := q.ObtenerCalculo(ctx, *l.CalculoID)
	if err != nil {
		return l, err
	}
	var res expensas.Resultado
	if err := json.Unmarshal(c.Resultado, &res); err != nil {
		return l, fmt.Errorf("leer el cálculo guardado: %w", err)
	}
	par, err := q.ParametrosVigentes(ctx, dbq.ParametrosVigentesParams{ConsorcioID: l.ConsorcioID, Fecha: l.Periodo})
	if err != nil {
		return l, err
	}
	venc := l.Periodo.DiaDelMes(int(par.DiaVencimiento))
	lid := l.ID
	hoy := fecha.Hoy()
	for _, u := range res.Unidades {
		ajuste := decimal.Zero
		for _, ln := range u.Lineas {
			if ln.Concepto == expensas.SaldoAnterior || ln.Importe.IsZero() {
				continue
			}
			if ln.Importe.IsNegative() {
				ajuste = ajuste.Add(ln.Importe.Neg())
				continue
			}
			tipo := "capital"
			if ln.Concepto == expensas.InteresDeuda {
				tipo = "interes"
			}
			if _, err := q.CrearPartida(ctx, dbq.CrearPartidaParams{
				ConsorcioID: l.ConsorcioID, UnidadID: u.UnidadID, LiquidacionID: &lid, Periodo: l.Periodo,
				Tipo: tipo, Concepto: string(ln.Concepto), Detalle: ln.Detalle, Importe: ln.Importe, Vencimiento: venc,
			}); err != nil {
				return l, err
			}
		}
		if ajuste.IsPositive() {
			if _, err := q.CrearPago(ctx, dbq.CrearPagoParams{
				ConsorcioID: l.ConsorcioID, UnidadID: u.UnidadID, Fecha: hoy, Importe: ajuste, Medio: "bonificacion",
				// La referencia es única en el consorcio y el ajuste anulado de una emisión
				// anterior la conserva: cada emisión lleva su propio sufijo.
				Referencia: prefijoAjuste + l.ID.String() + ":" + u.UnidadID.String() + ":" + uuid.NewString()[:8],
				CreadoPor:  tx.Usuario(),
			}); err != nil {
				return l, err
			}
		}
		// Saldo a favor (de pagos anteriores o del ajuste) contra lo nuevo.
		if err := cuentas.AplicarCredito(ctx, q, u.UnidadID); err != nil {
			return l, err
		}
	}
	return q.MarcarEmitida(ctx, dbq.MarcarEmitidaParams{Vencimiento: &venc, ID: l.ID})
}

func reabrirEmitida(ctx context.Context, q *dbq.Queries, l dbq.Liquidacion, motivo string) error {
	lid := l.ID
	n, err := q.AplicacionesDePagosEnLiquidacion(ctx, &lid)
	if err != nil {
		return err
	}
	if n > 0 {
		return api.Conflicto("la liquidación tiene pagos imputados: para reabrirla hay que anular esos pagos")
	}
	afectadas, err := q.UnidadesConPartidasDeLiquidacion(ctx, &lid)
	if err != nil {
		return err
	}
	m := "Reapertura de la liquidación: " + motivo
	ajustes, err := q.PagosDeAjusteDeLiquidacion(ctx, dbq.PagosDeAjusteDeLiquidacionParams{
		ConsorcioID: l.ConsorcioID, Prefijo: prefijoAjuste + l.ID.String() + ":"})
	if err != nil {
		return err
	}
	for _, p := range ajustes {
		if _, err := q.AnularAplicacionesDePago(ctx, dbq.AnularAplicacionesDePagoParams{Motivo: &m, PagoID: p.ID}); err != nil {
			return err
		}
		if _, err := q.AnularPago(ctx, dbq.AnularPagoParams{Motivo: &m, ID: p.ID}); err != nil {
			return err
		}
		afectadas = append(afectadas, p.UnidadID)
	}
	if _, err := q.AnularAplicacionesDeLiquidacion(ctx, dbq.AnularAplicacionesDeLiquidacionParams{Motivo: &m, LiquidacionID: &lid}); err != nil {
		return err
	}
	if _, err := q.AnularPartidasDeLiquidacion(ctx, dbq.AnularPartidasDeLiquidacionParams{Motivo: &m, LiquidacionID: &lid}); err != nil {
		return err
	}
	vistas := map[uuid.UUID]bool{}
	for _, u := range afectadas {
		if vistas[u] {
			continue
		}
		vistas[u] = true
		if err := cuentas.AplicarCredito(ctx, q, u); err != nil {
			return err
		}
	}
	return nil
}

// ── Rutas ────────────────────────────────────────────────────────────────────

// Rutas cuelga de /api/v1/administraciones/{administracionID}.
func (s *Servicio) Rutas(r chi.Router) {
	consorcio := func(tx api.Tx, r *http.Request, cid uuid.UUID) error {
		_, err := tx.Q.ObtenerConsorcio(r.Context(), cid)
		return err
	}
	periodoDeQuery := func(w http.ResponseWriter, r *http.Request) (fecha.Fecha, bool) {
		p, err := fecha.ParsePeriodo(r.URL.Query().Get("periodo"))
		if err != nil {
			httpx.Error(w, http.StatusBadRequest, "falta ?periodo=AAAA-MM")
			return p, false
		}
		return p, true
	}

	// ── Parámetros ──
	r.Get("/consorcios/{consorcioID}/parametros", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		if !ok {
			return
		}
		api.Leer(w, r, s.pool, "consorcio", func(tx api.Tx) ([]dbq.ParametrosConsorcio, error) {
			if err := consorcio(tx, r, cid); err != nil {
				return nil, err
			}
			return api.Lista(tx.Q.ListarParametros(r.Context(), cid))
		})
	})
	r.Post("/consorcios/{consorcioID}/parametros", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		var a altaParametros
		if !ok || !httpx.Leer(w, r, &a) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusCreated, "parámetros", func(tx api.Tx) (dbq.ParametrosConsorcio, error) {
			ctx := r.Context()
			switch {
			case !a.VigenteDesde.EsPrimeroDeMes():
				return dbq.ParametrosConsorcio{}, api.Invalido("vigente_desde tiene que ser el día 1 de un mes")
			case a.DiaVencimiento < 0 || a.DiaVencimiento > 28:
				return dbq.ParametrosConsorcio{}, api.Invalido("dia_vencimiento va de 1 a 28, o 0 para el último día del mes")
			case a.FondoReservaMensual.IsNegative() || !a.FondoReservaMensual.Equal(a.FondoReservaMensual.Round(2)):
				return dbq.ParametrosConsorcio{}, api.Invalido("fondo_reserva_mensual inválido")
			case a.FondoReservaMensual.IsPositive() && a.GrupoFondoID == nil:
				return dbq.ParametrosConsorcio{}, api.Invalido("con fondo de reserva hace falta grupo_fondo_id")
			}
			if err := consorcio(tx, r, cid); err != nil {
				return dbq.ParametrosConsorcio{}, err
			}
			if _, err := tx.Q.BloquearConsorcio(ctx, cid); err != nil {
				return dbq.ParametrosConsorcio{}, err
			}
			if err := vigenciaLibre(ctx, tx.Q, cid, a.VigenteDesde); err != nil {
				return dbq.ParametrosConsorcio{}, err
			}
			p, err := tx.Q.CrearParametros(ctx, dbq.CrearParametrosParams{ConsorcioID: cid, VigenteDesde: a.VigenteDesde,
				DiaVencimiento: a.DiaVencimiento, FondoReservaMensual: a.FondoReservaMensual, GrupoFondoID: a.GrupoFondoID})
			if err == nil {
				tx.Auditar("parametros_cargados", map[string]any{"consorcio_id": cid, "vigente_desde": a.VigenteDesde,
					"dia_vencimiento": a.DiaVencimiento, "fondo_reserva_mensual": a.FondoReservaMensual})
			}
			return p, err
		})
	})

	// ── Tasas de mora ──
	r.Get("/consorcios/{consorcioID}/tasas-mora", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		if !ok {
			return
		}
		api.Leer(w, r, s.pool, "consorcio", func(tx api.Tx) ([]dbq.TasaMora, error) {
			if err := consorcio(tx, r, cid); err != nil {
				return nil, err
			}
			return api.Lista(tx.Q.ListarTasas(r.Context(), cid))
		})
	})
	r.Post("/consorcios/{consorcioID}/tasas-mora", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		var a altaTasa
		if !ok || !httpx.Leer(w, r, &a) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusCreated, "tasa de mora", func(tx api.Tx) (dbq.TasaMora, error) {
			ctx := r.Context()
			a.Fundamento = strings.TrimSpace(a.Fundamento)
			switch {
			case !a.VigenteDesde.EsPrimeroDeMes():
				return dbq.TasaMora{}, api.Invalido("vigente_desde tiene que ser el día 1 de un mes")
			case a.TasaMensual.IsNegative() || !a.TasaMensual.LessThan(decimal.NewFromInt(1)) || -a.TasaMensual.Exponent() > 6:
				return dbq.TasaMora{}, api.Invalido("tasa_mensual va de 0 a menos de 1 (0.05 = 5 % mensual), con hasta 6 decimales")
			case a.Fundamento == "":
				return dbq.TasaMora{}, api.Invalido("falta el fundamento (reglamento, acta de asamblea...)")
			}
			if err := consorcio(tx, r, cid); err != nil {
				return dbq.TasaMora{}, err
			}
			if _, err := tx.Q.BloquearConsorcio(ctx, cid); err != nil {
				return dbq.TasaMora{}, err
			}
			if err := vigenciaLibre(ctx, tx.Q, cid, a.VigenteDesde); err != nil {
				return dbq.TasaMora{}, err
			}
			t, err := tx.Q.CrearTasa(ctx, dbq.CrearTasaParams{ConsorcioID: cid, VigenteDesde: a.VigenteDesde,
				TasaMensual: a.TasaMensual, Fundamento: a.Fundamento})
			if err == nil {
				tx.Auditar("tasa_mora_cargada", map[string]any{"consorcio_id": cid, "vigente_desde": a.VigenteDesde,
					"tasa_mensual": a.TasaMensual, "fundamento": a.Fundamento})
			}
			return t, err
		})
	})

	// ── Gastos ──
	r.Get("/consorcios/{consorcioID}/gastos", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		if !ok {
			return
		}
		p, ok := periodoDeQuery(w, r)
		if !ok {
			return
		}
		api.Leer(w, r, s.pool, "consorcio", func(tx api.Tx) ([]dbq.Gasto, error) {
			if err := consorcio(tx, r, cid); err != nil {
				return nil, err
			}
			return api.Lista(tx.Q.ListarGastos(r.Context(), dbq.ListarGastosParams{ConsorcioID: cid, Periodo: p}))
		})
	})
	r.Post("/consorcios/{consorcioID}/gastos", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		var a altaGasto
		if !ok || !httpx.Leer(w, r, &a) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusCreated, "gasto", func(tx api.Tx) (dbq.Gasto, error) {
			ctx := r.Context()
			a.Concepto = strings.TrimSpace(a.Concepto)
			a.Naturaleza = defecto(a.Naturaleza, "ordinaria")
			a.Habitualidad = defecto(a.Habitualidad, "recurrente")
			a.Financiacion = defecto(a.Financiacion, "expensas")
			a.Respaldo, a.Proveedor = texto(a.Respaldo), texto(a.Proveedor)
			switch {
			case !a.Periodo.EsPrimeroDeMes() || a.GrupoID == uuid.Nil || a.Concepto == "":
				return dbq.Gasto{}, api.Invalido("faltan periodo (AAAA-MM-01), grupo_id o concepto")
			case !importeValido(a.Importe, true):
				return dbq.Gasto{}, api.Invalido("importe inválido (distinto de 0, con hasta 2 decimales)")
			case a.Naturaleza != "ordinaria" && a.Naturaleza != "extraordinaria":
				return dbq.Gasto{}, api.Invalido("naturaleza: ordinaria o extraordinaria")
			case a.Habitualidad != "recurrente" && a.Habitualidad != "no_recurrente":
				return dbq.Gasto{}, api.Invalido("habitualidad: recurrente o no_recurrente")
			case a.Financiacion != "expensas" && a.Financiacion != "fondo_reserva":
				return dbq.Gasto{}, api.Invalido("financiacion: expensas o fondo_reserva")
			case a.Naturaleza == "extraordinaria" && a.Respaldo == nil:
				return dbq.Gasto{}, api.Invalido("un gasto extraordinario necesita respaldo (acta o autorización)")
			}
			if err := consorcio(tx, r, cid); err != nil {
				return dbq.Gasto{}, err
			}
			if _, err := tx.Q.BloquearConsorcio(ctx, cid); err != nil {
				return dbq.Gasto{}, err
			}
			if err := periodoAbierto(ctx, tx.Q, cid, a.Periodo.SumarMeses(1)); err != nil {
				return dbq.Gasto{}, err
			}
			g, err := tx.Q.CrearGasto(ctx, dbq.CrearGastoParams{ConsorcioID: cid, Periodo: a.Periodo, GrupoID: a.GrupoID,
				Concepto: a.Concepto, Proveedor: a.Proveedor, Importe: a.Importe, Naturaleza: a.Naturaleza,
				Habitualidad: a.Habitualidad, Financiacion: a.Financiacion, Respaldo: a.Respaldo})
			if err == nil {
				tx.Auditar("gasto_cargado", map[string]any{"gasto_id": g.ID, "consorcio_id": cid, "periodo": a.Periodo,
					"importe": a.Importe, "concepto": a.Concepto})
			}
			return g, err
		})
	})
	r.Post("/gastos/{gastoID}/anular", func(w http.ResponseWriter, r *http.Request) {
		gid, ok := api.ID(w, r, "gastoID", "gasto")
		var a conMotivo
		if !ok || !httpx.Leer(w, r, &a) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusOK, "gasto", func(tx api.Tx) (dbq.Gasto, error) {
			ctx := r.Context()
			motivo := strings.TrimSpace(a.Motivo)
			if motivo == "" {
				return dbq.Gasto{}, api.Invalido("falta el motivo")
			}
			g, err := tx.Q.ObtenerGasto(ctx, gid)
			if err != nil {
				return g, err
			}
			if _, err := tx.Q.BloquearConsorcio(ctx, g.ConsorcioID); err != nil {
				return g, err
			}
			if g.AnuladoEn != nil {
				return g, api.Conflicto("el gasto ya está anulado")
			}
			if err := periodoAbierto(ctx, tx.Q, g.ConsorcioID, g.Periodo.SumarMeses(1)); err != nil {
				return g, err
			}
			g, err = tx.Q.AnularGasto(ctx, dbq.AnularGastoParams{Motivo: &motivo, ID: gid})
			if err == nil {
				tx.Auditar("gasto_anulado", map[string]any{"gasto_id": gid, "motivo": motivo})
			}
			return g, err
		})
	})

	// ── Cargos particulares ──
	r.Get("/consorcios/{consorcioID}/cargos", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		if !ok {
			return
		}
		p, ok := periodoDeQuery(w, r)
		if !ok {
			return
		}
		api.Leer(w, r, s.pool, "consorcio", func(tx api.Tx) ([]dbq.CargoParticular, error) {
			if err := consorcio(tx, r, cid); err != nil {
				return nil, err
			}
			return api.Lista(tx.Q.ListarCargos(r.Context(), dbq.ListarCargosParams{ConsorcioID: cid, Periodo: p}))
		})
	})
	r.Post("/consorcios/{consorcioID}/cargos", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		var a altaCargo
		if !ok || !httpx.Leer(w, r, &a) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusCreated, "cargo particular", func(tx api.Tx) (dbq.CargoParticular, error) {
			ctx := r.Context()
			a.Concepto = strings.TrimSpace(a.Concepto)
			switch {
			case !a.Periodo.EsPrimeroDeMes() || a.UnidadID == uuid.Nil || a.Concepto == "":
				return dbq.CargoParticular{}, api.Invalido("faltan periodo (AAAA-MM-01), unidad_id o concepto")
			case !importeValido(a.Importe, true):
				return dbq.CargoParticular{}, api.Invalido("importe inválido (distinto de 0, con hasta 2 decimales; negativo = bonificación)")
			}
			if err := consorcio(tx, r, cid); err != nil {
				return dbq.CargoParticular{}, err
			}
			if _, err := tx.Q.BloquearConsorcio(ctx, cid); err != nil {
				return dbq.CargoParticular{}, err
			}
			if err := periodoAbierto(ctx, tx.Q, cid, a.Periodo); err != nil {
				return dbq.CargoParticular{}, err
			}
			c, err := tx.Q.CrearCargo(ctx, dbq.CrearCargoParams{ConsorcioID: cid, UnidadID: a.UnidadID, Periodo: a.Periodo,
				Concepto: a.Concepto, Importe: a.Importe})
			if err == nil {
				tx.Auditar("cargo_particular_cargado", map[string]any{"cargo_id": c.ID, "unidad_id": a.UnidadID,
					"periodo": a.Periodo, "importe": a.Importe})
			}
			return c, err
		})
	})
	r.Post("/cargos/{cargoID}/anular", func(w http.ResponseWriter, r *http.Request) {
		id, ok := api.ID(w, r, "cargoID", "cargo particular")
		var a conMotivo
		if !ok || !httpx.Leer(w, r, &a) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusOK, "cargo particular", func(tx api.Tx) (dbq.CargoParticular, error) {
			ctx := r.Context()
			motivo := strings.TrimSpace(a.Motivo)
			if motivo == "" {
				return dbq.CargoParticular{}, api.Invalido("falta el motivo")
			}
			c, err := tx.Q.ObtenerCargo(ctx, id)
			if err != nil {
				return c, err
			}
			if _, err := tx.Q.BloquearConsorcio(ctx, c.ConsorcioID); err != nil {
				return c, err
			}
			if c.AnuladoEn != nil {
				return c, api.Conflicto("el cargo ya está anulado")
			}
			if err := periodoAbierto(ctx, tx.Q, c.ConsorcioID, c.Periodo); err != nil {
				return c, err
			}
			c, err = tx.Q.AnularCargo(ctx, dbq.AnularCargoParams{Motivo: &motivo, ID: id})
			if err == nil {
				tx.Auditar("cargo_particular_anulado", map[string]any{"cargo_id": id, "motivo": motivo})
			}
			return c, err
		})
	})

	// ── Liquidaciones ──
	r.Get("/consorcios/{consorcioID}/liquidaciones", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		if !ok {
			return
		}
		api.Leer(w, r, s.pool, "consorcio", func(tx api.Tx) ([]dbq.Liquidacion, error) {
			if err := consorcio(tx, r, cid); err != nil {
				return nil, err
			}
			return api.Lista(tx.Q.ListarLiquidaciones(r.Context(), cid))
		})
	})
	r.Post("/consorcios/{consorcioID}/liquidaciones", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		var a altaLiquidacion
		if !ok || !httpx.Leer(w, r, &a) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusCreated, "liquidación", func(tx api.Tx) (dbq.Liquidacion, error) {
			ctx := r.Context()
			if !a.Periodo.EsPrimeroDeMes() {
				return dbq.Liquidacion{}, api.Invalido("periodo tiene que ser el día 1 de un mes (AAAA-MM-01)")
			}
			if err := consorcio(tx, r, cid); err != nil {
				return dbq.Liquidacion{}, err
			}
			if _, err := tx.Q.BloquearConsorcio(ctx, cid); err != nil {
				return dbq.Liquidacion{}, err
			}
			if hay, err := tx.Q.HayPosteriorCerrada(ctx, dbq.HayPosteriorCerradaParams{ConsorcioID: cid, Periodo: a.Periodo}); err != nil || hay {
				if err == nil {
					err = api.Conflicto("ya hay una liquidación posterior aprobada o emitida")
				}
				return dbq.Liquidacion{}, err
			}
			l, err := tx.Q.CrearLiquidacion(ctx, dbq.CrearLiquidacionParams{ConsorcioID: cid, Periodo: a.Periodo})
			if err == nil {
				tx.Auditar("liquidacion_creada", map[string]any{"liquidacion_id": l.ID, "periodo": a.Periodo})
			}
			return l, err
		})
	})
	r.Get("/liquidaciones/{liquidacionID}", func(w http.ResponseWriter, r *http.Request) {
		id, ok := api.ID(w, r, "liquidacionID", "liquidación")
		if !ok {
			return
		}
		api.Leer(w, r, s.pool, "liquidación", func(tx api.Tx) (Detalle, error) {
			l, err := tx.Q.ObtenerLiquidacion(r.Context(), id)
			if err != nil {
				return Detalle{}, err
			}
			return detalle(r.Context(), tx.Q, l)
		})
	})

	r.Post("/liquidaciones/{liquidacionID}/calcular", func(w http.ResponseWriter, r *http.Request) {
		id, ok := api.ID(w, r, "liquidacionID", "liquidación")
		var a pedidoCalculo
		if !ok || !httpx.LeerOpcional(w, r, &a) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusOK, "liquidación", func(tx api.Tx) (Detalle, error) {
			ctx := r.Context()
			l, err := obtenerBloqueada(ctx, tx.Q, id)
			if err != nil {
				return Detalle{}, err
			}
			if l.Estado != "borrador" && l.Estado != "calculada" {
				return Detalle{}, api.Conflicto("la liquidación está " + l.Estado + ": no se recalcula")
			}
			fc := fecha.Hoy()
			if a.FechaCalculo != nil {
				fc = *a.FechaCalculo
			}
			if fc.Antes(l.Periodo.SumarMeses(-1)) {
				return Detalle{}, api.Invalido("la fecha de cálculo no puede ser anterior al mes de los gastos")
			}
			e, tasaID, err := armarEntrada(ctx, tx.Q, l, fc)
			if err != nil {
				return Detalle{}, err
			}
			res, err := expensas.Calcular(e)
			if err != nil {
				return Detalle{}, api.Conflicto("no se puede calcular: " + err.Error())
			}
			entrada, err := json.Marshal(e)
			if err != nil {
				return Detalle{}, err
			}
			resultado, err := json.Marshal(res)
			if err != nil {
				return Detalle{}, err
			}
			c, err := tx.Q.GuardarCalculo(ctx, dbq.GuardarCalculoParams{ConsorcioID: l.ConsorcioID, LiquidacionID: l.ID,
				FechaCalculo: fc, TasaMensual: e.TasaMensual, TasaID: tasaID, Entrada: entrada, Resultado: resultado,
				TotalCargos: res.TotalCargos, CalculadoPor: tx.Usuario()})
			if err != nil {
				return Detalle{}, err
			}
			if l, err = tx.Q.MarcarCalculada(ctx, dbq.MarcarCalculadaParams{CalculoID: &c.ID, ID: l.ID}); err != nil {
				return Detalle{}, err
			}
			tx.Auditar("liquidacion_calculada", map[string]any{"liquidacion_id": l.ID, "calculo_id": c.ID,
				"fecha_calculo": fc, "total_cargos": res.TotalCargos})
			return detalle(ctx, tx.Q, l)
		})
	})

	r.Post("/liquidaciones/{liquidacionID}/condonaciones", func(w http.ResponseWriter, r *http.Request) {
		id, ok := api.ID(w, r, "liquidacionID", "liquidación")
		var a altaCondonacion
		if !ok || !httpx.Leer(w, r, &a) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusOK, "condonación", func(tx api.Tx) (Detalle, error) {
			ctx := r.Context()
			a.Motivo = strings.TrimSpace(a.Motivo)
			if a.UnidadID == uuid.Nil || a.Motivo == "" {
				return Detalle{}, api.Invalido("faltan unidad_id o motivo")
			}
			l, err := obtenerBloqueada(ctx, tx.Q, id)
			if err != nil {
				return Detalle{}, err
			}
			if err := periodoAbierto(ctx, tx.Q, l.ConsorcioID, l.Periodo); err != nil {
				return Detalle{}, err
			}
			if err := tx.Q.Condonar(ctx, dbq.CondonarParams{ConsorcioID: l.ConsorcioID, LiquidacionID: l.ID,
				UnidadID: a.UnidadID, Motivo: a.Motivo, CreadoPor: tx.Usuario()}); err != nil {
				return Detalle{}, err
			}
			tx.Auditar("interes_condonado", map[string]any{"liquidacion_id": l.ID, "unidad_id": a.UnidadID, "motivo": a.Motivo})
			if l, err = tx.Q.ObtenerLiquidacion(ctx, id); err != nil {
				return Detalle{}, err
			}
			return detalle(ctx, tx.Q, l)
		})
	})
	r.Delete("/liquidaciones/{liquidacionID}/condonaciones/{unidadID}", func(w http.ResponseWriter, r *http.Request) {
		id, ok := api.ID(w, r, "liquidacionID", "liquidación")
		if !ok {
			return
		}
		uid, ok := api.ID(w, r, "unidadID", "unidad")
		if !ok {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusOK, "condonación", func(tx api.Tx) (Detalle, error) {
			ctx := r.Context()
			l, err := obtenerBloqueada(ctx, tx.Q, id)
			if err != nil {
				return Detalle{}, err
			}
			if err := periodoAbierto(ctx, tx.Q, l.ConsorcioID, l.Periodo); err != nil {
				return Detalle{}, err
			}
			n, err := tx.Q.QuitarCondonacion(ctx, dbq.QuitarCondonacionParams{LiquidacionID: id, UnidadID: uid})
			if err != nil {
				return Detalle{}, err
			}
			if n == 0 {
				return Detalle{}, pgx.ErrNoRows
			}
			tx.Auditar("condonacion_quitada", map[string]any{"liquidacion_id": id, "unidad_id": uid})
			if l, err = tx.Q.ObtenerLiquidacion(ctx, id); err != nil {
				return Detalle{}, err
			}
			return detalle(ctx, tx.Q, l)
		})
	})

	// Aprobar, emitir y reabrir: solo administradores.
	transicion := func(ruta, accion string, fn func(ctx context.Context, tx api.Tx, l dbq.Liquidacion, motivo string) (dbq.Liquidacion, error), pideMotivo bool) {
		r.Post("/liquidaciones/{liquidacionID}/"+ruta, func(w http.ResponseWriter, r *http.Request) {
			id, ok := api.ID(w, r, "liquidacionID", "liquidación")
			var a conMotivo
			if !ok || !httpx.LeerOpcional(w, r, &a) {
				return
			}
			api.Escribir(w, r, s.pool, http.StatusOK, "liquidación", func(tx api.Tx) (Detalle, error) {
				ctx := r.Context()
				if !tx.EsAdmin() {
					return Detalle{}, api.Prohibido("solo un administrador puede " + ruta + " una liquidación")
				}
				motivo := strings.TrimSpace(a.Motivo)
				if pideMotivo && motivo == "" {
					return Detalle{}, api.Invalido("falta el motivo")
				}
				l, err := obtenerBloqueada(ctx, tx.Q, id)
				if err != nil {
					return Detalle{}, err
				}
				anterior := l.Estado
				if l, err = fn(ctx, tx, l, motivo); err != nil {
					return Detalle{}, err
				}
				tx.Auditar(accion, map[string]any{"liquidacion_id": id, "periodo": l.Periodo,
					"estado_anterior": anterior, "motivo": motivo})
				return detalle(ctx, tx.Q, l)
			})
		})
	}
	anteriorEmitida := func(ctx context.Context, q *dbq.Queries, l dbq.Liquidacion) error {
		hay, err := q.HayAnteriorAbierta(ctx, dbq.HayAnteriorAbiertaParams{ConsorcioID: l.ConsorcioID, Periodo: l.Periodo})
		if err == nil && hay {
			err = api.Conflicto("hay una liquidación anterior sin emitir: se emiten en orden")
		}
		return err
	}

	transicion("aprobar", "liquidacion_aprobada", func(ctx context.Context, tx api.Tx, l dbq.Liquidacion, _ string) (dbq.Liquidacion, error) {
		if l.Estado != "calculada" {
			return l, api.Conflicto("solo se aprueba una liquidación calculada (está " + l.Estado + ")")
		}
		if err := anteriorEmitida(ctx, tx.Q, l); err != nil {
			return l, err
		}
		return tx.Q.MarcarAprobada(ctx, l.ID)
	}, false)

	transicion("emitir", "liquidacion_emitida", func(ctx context.Context, tx api.Tx, l dbq.Liquidacion, _ string) (dbq.Liquidacion, error) {
		if l.Estado != "aprobada" {
			return l, api.Conflicto("solo se emite una liquidación aprobada (está " + l.Estado + ")")
		}
		if err := anteriorEmitida(ctx, tx.Q, l); err != nil {
			return l, err
		}
		return emitir(ctx, tx, l)
	}, false)

	transicion("reabrir", "liquidacion_reabierta", func(ctx context.Context, tx api.Tx, l dbq.Liquidacion, motivo string) (dbq.Liquidacion, error) {
		switch l.Estado {
		case "aprobada":
		case "emitida":
			hay, err := tx.Q.HayPosteriorCerrada(ctx, dbq.HayPosteriorCerradaParams{ConsorcioID: l.ConsorcioID, Periodo: l.Periodo})
			if err != nil {
				return l, err
			}
			if hay {
				return l, api.Conflicto("la liquidación siguiente ya está aprobada o emitida: reabrí esa primero")
			}
			if err := reabrirEmitida(ctx, tx.Q, l, motivo); err != nil {
				return l, err
			}
		default:
			return l, api.Conflicto("solo se reabre una liquidación aprobada o emitida (está " + l.Estado + ")")
		}
		return tx.Q.MarcarReabierta(ctx, l.ID)
	}, true)
}
