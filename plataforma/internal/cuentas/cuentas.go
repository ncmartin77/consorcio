// Package cuentas: cuenta corriente de cada unidad (partidas, pagos, saldo a favor).
//
//   - Partida: algo que la unidad debe (capital o interés), de una liquidación emitida o de
//     la deuda inicial que se trae al migrar.
//   - Pago: lo que la unidad pagó. Se imputa al registrarlo (art. 903 CCyC): primero los
//     intereses, del más viejo al más nuevo; después el capital, del más viejo al más nuevo.
//   - Lo que un pago no alcanza a aplicar queda como saldo a favor y se aplica solo a las
//     partidas nuevas (al emitir una liquidación o al anular otro pago).
//   - Nada se borra: pagos, partidas y aplicaciones se anulan con motivo.
//
// Invariante: una unidad nunca tiene a la vez saldo a favor y partidas pendientes.
package cuentas

import (
	"context"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shopspring/decimal"

	"github.com/ncmartin77/consorcio/plataforma/internal/expensas"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/api"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/fecha"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/httpx"
)

type Servicio struct{ pool *pgxpool.Pool }

func NuevoServicio(pool *pgxpool.Pool) *Servicio { return &Servicio{pool: pool} }

var mediosValidos = map[string]bool{
	"efectivo": true, "transferencia": true, "cheque": true, "deposito": true, "bonificacion": true, "otro": true,
}

func partidasParaImputar(ctx context.Context, q *dbq.Queries, unidadID uuid.UUID) ([]expensas.Partida, error) {
	filas, err := q.PartidasConPendiente(ctx, unidadID)
	if err != nil {
		return nil, err
	}
	ps := make([]expensas.Partida, 0, len(filas))
	for _, f := range filas {
		ps = append(ps, expensas.Partida{ID: f.ID, EsInteres: f.Tipo == "interes", Periodo: f.Periodo, Pendiente: f.Pendiente})
	}
	return ps, nil
}

// Imputar aplica `importe` del pago a las partidas pendientes de la unidad. Devuelve lo
// que sobró (saldo a favor).
func Imputar(ctx context.Context, q *dbq.Queries, unidadID, pagoID uuid.UUID, importe decimal.Decimal, origen string) (decimal.Decimal, error) {
	ps, err := partidasParaImputar(ctx, q, unidadID)
	if err != nil {
		return decimal.Zero, err
	}
	apls, sobra := expensas.Imputar(importe, ps)
	for _, a := range apls {
		if err := q.CrearAplicacion(ctx, dbq.CrearAplicacionParams{
			UnidadID: unidadID, PagoID: pagoID, PartidaID: a.PartidaID, Importe: a.Importe, Origen: origen,
		}); err != nil {
			return decimal.Zero, err
		}
	}
	return sobra, nil
}

// AplicarCredito usa el saldo a favor de la unidad (pagos con importe sin aplicar, del más
// viejo al más nuevo) para cancelar sus partidas pendientes.
func AplicarCredito(ctx context.Context, q *dbq.Queries, unidadID uuid.UUID) error {
	pagos, err := q.PagosConCredito(ctx, unidadID)
	if err != nil {
		return err
	}
	for _, p := range pagos {
		sobra, err := Imputar(ctx, q, unidadID, p.ID, p.Disponible, "credito")
		if err != nil {
			return err
		}
		if sobra.Equal(p.Disponible) {
			return nil // no quedan partidas pendientes
		}
	}
	return nil
}

type altaPago struct {
	UnidadID   uuid.UUID       `json:"unidad_id"`
	Fecha      fecha.Fecha     `json:"fecha"`
	Importe    decimal.Decimal `json:"importe"`
	Medio      string          `json:"medio"`
	Referencia string          `json:"referencia"`
}

type anulacion struct {
	Motivo string `json:"motivo"`
}

type deudaInicial struct {
	Periodo     fecha.Fecha     `json:"periodo"`
	Importe     decimal.Decimal `json:"importe"`
	Vencimiento fecha.Fecha     `json:"vencimiento"`
	Detalle     string          `json:"detalle"`
}

type PagoRegistrado struct {
	Pago        dbq.Pago        `json:"pago"`
	Aplicado    decimal.Decimal `json:"aplicado"`
	SaldoAFavor decimal.Decimal `json:"saldo_a_favor"` // lo que sobró de este pago
}

type Cuenta struct {
	UnidadID     uuid.UUID                 `json:"unidad_id"`
	Partidas     []dbq.PartidasDeUnidadRow `json:"partidas"`
	Pagos        []dbq.PagosDeUnidadRow    `json:"pagos"`
	Aplicaciones []dbq.Aplicacion          `json:"aplicaciones"`
	Deuda        decimal.Decimal           `json:"deuda"`         // suma de lo pendiente
	SaldoAFavor  decimal.Decimal           `json:"saldo_a_favor"` // pagos sin aplicar
	Saldo        decimal.Decimal           `json:"saldo"`         // deuda − saldo a favor (>0 debe)
}

func cuenta(ctx context.Context, q *dbq.Queries, unidadID uuid.UUID) (Cuenta, error) {
	c := Cuenta{UnidadID: unidadID, Deuda: decimal.Zero, SaldoAFavor: decimal.Zero}
	var err error
	if c.Partidas, err = api.Lista(q.PartidasDeUnidad(ctx, unidadID)); err != nil {
		return c, err
	}
	if c.Pagos, err = api.Lista(q.PagosDeUnidad(ctx, unidadID)); err != nil {
		return c, err
	}
	if c.Aplicaciones, err = api.Lista(q.AplicacionesDeUnidad(ctx, unidadID)); err != nil {
		return c, err
	}
	for _, p := range c.Partidas {
		if p.AnuladoEn == nil {
			c.Deuda = c.Deuda.Add(p.Pendiente)
		}
	}
	for _, p := range c.Pagos {
		if p.AnuladoEn == nil {
			c.SaldoAFavor = c.SaldoAFavor.Add(p.Importe.Sub(p.Aplicado))
		}
	}
	c.Saldo = c.Deuda.Sub(c.SaldoAFavor)
	return c, nil
}

func importeValido(d decimal.Decimal) bool {
	return d.IsPositive() && d.Equal(d.Round(2)) && d.LessThan(decimal.New(1, 12))
}

// Rutas cuelga de /api/v1/administraciones/{administracionID}.
func (s *Servicio) Rutas(r chi.Router) {
	r.Get("/unidades/{unidadID}/cuenta", func(w http.ResponseWriter, r *http.Request) {
		uid, ok := api.ID(w, r, "unidadID", "unidad")
		if !ok {
			return
		}
		api.Leer(w, r, s.pool, "unidad", func(tx api.Tx) (Cuenta, error) {
			if _, err := tx.Q.ObtenerUnidad(r.Context(), uid); err != nil {
				return Cuenta{}, err
			}
			return cuenta(r.Context(), tx.Q, uid)
		})
	})

	// Deuda que se trae al migrar: solo antes de la primera liquidación emitida.
	r.Post("/unidades/{unidadID}/deuda-inicial", func(w http.ResponseWriter, r *http.Request) {
		uid, ok := api.ID(w, r, "unidadID", "unidad")
		var d deudaInicial
		if !ok || !httpx.Leer(w, r, &d) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusCreated, "deuda inicial", func(tx api.Tx) (dbq.Partida, error) {
			ctx := r.Context()
			if !tx.EsAdmin() {
				return dbq.Partida{}, api.Prohibido("solo un administrador carga la deuda inicial")
			}
			if !d.Periodo.EsPrimeroDeMes() || d.Vencimiento.EsCero() || !importeValido(d.Importe) {
				return dbq.Partida{}, api.Invalido("faltan o son inválidos: periodo (AAAA-MM-01), vencimiento o importe")
			}
			u, err := tx.Q.ObtenerUnidad(ctx, uid)
			if err != nil {
				return dbq.Partida{}, err
			}
			if _, err := tx.Q.BloquearConsorcio(ctx, u.ConsorcioID); err != nil {
				return dbq.Partida{}, err
			}
			if hay, err := tx.Q.HayEmitidas(ctx, u.ConsorcioID); err != nil || hay {
				if err == nil {
					err = api.Conflicto("el consorcio ya tiene liquidaciones emitidas: la deuda se corrige con un cargo particular")
				}
				return dbq.Partida{}, err
			}
			detalle := strings.TrimSpace(d.Detalle)
			if detalle == "" {
				detalle = "Deuda inicial (migración)"
			}
			p, err := tx.Q.CrearPartida(ctx, dbq.CrearPartidaParams{
				ConsorcioID: u.ConsorcioID, UnidadID: uid, Periodo: d.Periodo, Tipo: "capital",
				Concepto: "deuda_inicial", Detalle: detalle, Importe: d.Importe, Vencimiento: d.Vencimiento,
				DeudaInicial: true,
			})
			if err != nil {
				return p, err
			}
			if err := AplicarCredito(ctx, tx.Q, uid); err != nil {
				return p, err
			}
			tx.Auditar("deuda_inicial_cargada", map[string]any{"unidad_id": uid, "partida_id": p.ID, "importe": d.Importe})
			return p, nil
		})
	})

	r.Post("/consorcios/{consorcioID}/pagos", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		var a altaPago
		if !ok || !httpx.Leer(w, r, &a) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusCreated, "pago", func(tx api.Tx) (PagoRegistrado, error) {
			ctx := r.Context()
			a.Referencia = strings.TrimSpace(a.Referencia)
			if a.Medio == "" {
				a.Medio = "transferencia"
			}
			switch {
			case a.UnidadID == uuid.Nil || a.Fecha.EsCero() || a.Referencia == "":
				return PagoRegistrado{}, api.Invalido("faltan unidad_id, fecha o referencia")
			case !importeValido(a.Importe):
				return PagoRegistrado{}, api.Invalido("importe inválido (mayor que 0, con hasta 2 decimales)")
			case !mediosValidos[a.Medio]:
				return PagoRegistrado{}, api.Invalido("medio inválido")
			case a.Fecha.Despues(fecha.Hoy()):
				return PagoRegistrado{}, api.Invalido("la fecha del pago no puede ser futura")
			}
			if _, err := tx.Q.BloquearConsorcio(ctx, cid); err != nil {
				return PagoRegistrado{}, err
			}
			u, err := tx.Q.ObtenerUnidad(ctx, a.UnidadID)
			if err != nil || u.ConsorcioID != cid {
				if err == nil {
					err = api.Invalido("la unidad no es de este consorcio")
				}
				return PagoRegistrado{}, err
			}
			p, err := tx.Q.CrearPago(ctx, dbq.CrearPagoParams{
				ConsorcioID: cid, UnidadID: a.UnidadID, Fecha: a.Fecha, Importe: a.Importe,
				Medio: a.Medio, Referencia: a.Referencia, CreadoPor: tx.Usuario(),
			})
			if err != nil {
				return PagoRegistrado{}, err
			}
			sobra, err := Imputar(ctx, tx.Q, a.UnidadID, p.ID, a.Importe, "pago")
			if err != nil {
				return PagoRegistrado{}, err
			}
			tx.Auditar("pago_registrado", map[string]any{
				"pago_id": p.ID, "unidad_id": a.UnidadID, "importe": a.Importe, "referencia": a.Referencia, "saldo_a_favor": sobra})
			return PagoRegistrado{Pago: p, Aplicado: a.Importe.Sub(sobra), SaldoAFavor: sobra}, nil
		})
	})

	r.Post("/pagos/{pagoID}/anular", func(w http.ResponseWriter, r *http.Request) {
		pid, ok := api.ID(w, r, "pagoID", "pago")
		var a anulacion
		if !ok || !httpx.Leer(w, r, &a) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusOK, "pago", func(tx api.Tx) (dbq.Pago, error) {
			ctx := r.Context()
			motivo := strings.TrimSpace(a.Motivo)
			if motivo == "" {
				return dbq.Pago{}, api.Invalido("falta el motivo")
			}
			p, err := tx.Q.ObtenerPago(ctx, pid)
			if err != nil {
				return p, err
			}
			if _, err := tx.Q.BloquearConsorcio(ctx, p.ConsorcioID); err != nil {
				return p, err
			}
			if p.AnuladoEn != nil {
				return p, api.Conflicto("el pago ya está anulado")
			}
			if p.Medio == "bonificacion" && strings.HasPrefix(p.Referencia, "liquidacion:") {
				return p, api.Conflicto("es un ajuste de una liquidación: se anula reabriendo la liquidación")
			}
			if _, err := tx.Q.AnularAplicacionesDePago(ctx, dbq.AnularAplicacionesDePagoParams{Motivo: &motivo, PagoID: pid}); err != nil {
				return p, err
			}
			p, err = tx.Q.AnularPago(ctx, dbq.AnularPagoParams{Motivo: &motivo, ID: pid})
			if err != nil {
				return p, err
			}
			// Lo que este pago cubría vuelve a deberse; si la unidad tiene saldo a favor de
			// otros pagos, se aplica ahora.
			if err := AplicarCredito(ctx, tx.Q, p.UnidadID); err != nil {
				return p, err
			}
			tx.Auditar("pago_anulado", map[string]any{"pago_id": pid, "motivo": motivo})
			return p, nil
		})
	})
}
