// Package fecha: un día calendario (sin hora ni zona), para vigencias y vínculos.
// Se guarda como date en Postgres y viaja como "2006-01-02" en JSON.
package fecha

import (
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgtype"
)

const formato = "2006-01-02"

type Fecha struct{ t time.Time }

func Nueva(anio int, mes time.Month, dia int) Fecha {
	return Fecha{time.Date(anio, mes, dia, 0, 0, 0, 0, time.UTC)}
}

// Hoy en Argentina (UTC-3, sin horario de verano).
func Hoy() Fecha {
	ahora := time.Now().In(time.FixedZone("ART", -3*3600))
	return Nueva(ahora.Year(), ahora.Month(), ahora.Day())
}

func Parse(s string) (Fecha, error) {
	t, err := time.Parse(formato, s)
	if err != nil {
		return Fecha{}, fmt.Errorf("fecha inválida %q (formato AAAA-MM-DD)", s)
	}
	return Fecha{t}, nil
}

func (f Fecha) String() string       { return f.t.Format(formato) }
func (f Fecha) Time() time.Time      { return f.t }
func (f Fecha) EsCero() bool         { return f.t.IsZero() }
func (f Fecha) Antes(o Fecha) bool   { return f.t.Before(o.t) }
func (f Fecha) Despues(o Fecha) bool { return f.t.After(o.t) }

func (f Fecha) MarshalJSON() ([]byte, error) { return json.Marshal(f.String()) }

func (f *Fecha) UnmarshalJSON(b []byte) error {
	var s string
	if err := json.Unmarshal(b, &s); err != nil {
		return errors.New("la fecha tiene que ser un texto AAAA-MM-DD")
	}
	p, err := Parse(s)
	if err != nil {
		return err
	}
	*f = p
	return nil
}

// pgx: date ↔ Fecha.
func (f *Fecha) ScanDate(d pgtype.Date) error {
	if !d.Valid { // p. ej. max() sin filas: queda la fecha cero (ver EsCero)
		*f = Fecha{}
		return nil
	}
	if d.InfinityModifier != pgtype.Finite {
		return errors.New("fecha infinita no soportada")
	}
	*f = Fecha{d.Time.UTC()}
	return nil
}

func (f Fecha) DateValue() (pgtype.Date, error) {
	return pgtype.Date{Time: f.t, Valid: true}, nil
}
