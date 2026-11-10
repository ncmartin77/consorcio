package expensas

import (
	"sort"

	"github.com/google/uuid"
	"github.com/shopspring/decimal"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/fecha"
)

// Partida: algo que la unidad debe (un cargo o un interés de un período).
type Partida struct {
	ID        uuid.UUID
	EsInteres bool
	Periodo   fecha.Fecha     // primer día del período liquidado
	Pendiente decimal.Decimal // lo que falta pagar de esta partida
}

type Aplicacion struct {
	PartidaID uuid.UUID       `json:"partida_id"`
	Importe   decimal.Decimal `json:"importe"`
}

// Imputar reparte un pago entre las partidas pendientes (art. 903 CCyC): primero los
// intereses, del más viejo al más nuevo; después el capital, del más viejo al más nuevo.
// Devuelve las aplicaciones y lo que sobra (saldo a favor de la unidad).
func Imputar(pago decimal.Decimal, partidas []Partida) (aplicaciones []Aplicacion, sobrante decimal.Decimal) {
	ps := append([]Partida(nil), partidas...)
	sort.SliceStable(ps, func(i, j int) bool {
		if ps[i].EsInteres != ps[j].EsInteres {
			return ps[i].EsInteres
		}
		return ps[i].Periodo.Antes(ps[j].Periodo)
	})
	resto := pago
	for _, p := range ps {
		if !resto.IsPositive() {
			break
		}
		if !p.Pendiente.IsPositive() {
			continue
		}
		aplicar := decimal.Min(resto, p.Pendiente)
		aplicaciones = append(aplicaciones, Aplicacion{PartidaID: p.ID, Importe: aplicar})
		resto = resto.Sub(aplicar)
	}
	return aplicaciones, resto
}
