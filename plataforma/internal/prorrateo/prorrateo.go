// Package prorrateo: grupos de prorrateo y coeficientes de cada unidad con vigencia.
//
// Una tabla de coeficientes se carga entera para un grupo y rige desde una fecha:
// cierra la anterior (vigente_hasta = desde) sin borrarla. Tiene que sumar exactamente
// 100 %: el motor de expensas (etapa 3) reparte con estos números y la suma de los
// cargos tiene que dar el total del gasto.
package prorrateo

import (
	"fmt"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shopspring/decimal"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/api"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/fecha"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/httpx"
)

var cien = decimal.NewFromInt(100)

const maxDecimales = 6 // numeric(9,6)

type Servicio struct{ pool *pgxpool.Pool }

func NuevoServicio(pool *pgxpool.Pool) *Servicio { return &Servicio{pool: pool} }

type altaGrupo struct {
	Nombre      string  `json:"nombre"`
	Descripcion *string `json:"descripcion"`
}

type Coeficiente struct {
	UnidadID   uuid.UUID       `json:"unidad_id"`
	Porcentaje decimal.Decimal `json:"porcentaje"`
}

type tabla struct {
	VigenteDesde fecha.Fecha   `json:"vigente_desde"`
	Coeficientes []Coeficiente `json:"coeficientes"`
}

type Vigentes struct {
	GrupoID      uuid.UUID                     `json:"grupo_id"`
	Fecha        fecha.Fecha                   `json:"fecha"`
	Coeficientes []dbq.CoeficientesVigentesRow `json:"coeficientes"`
	Suma         decimal.Decimal               `json:"suma"`
	SumaCorrecta bool                          `json:"suma_correcta"` // exactamente 100
}

// ValidarTabla revisa una tabla nueva antes de guardarla.
func ValidarTabla(cs []Coeficiente) error {
	if len(cs) == 0 {
		return fmt.Errorf("la tabla no tiene coeficientes")
	}
	vistas := map[uuid.UUID]bool{}
	suma := decimal.Zero
	for _, c := range cs {
		switch {
		case c.UnidadID == uuid.Nil:
			return fmt.Errorf("falta unidad_id en un coeficiente")
		case vistas[c.UnidadID]:
			return fmt.Errorf("la unidad %s aparece dos veces", c.UnidadID)
		case c.Porcentaje.IsNegative() || c.Porcentaje.GreaterThan(cien):
			return fmt.Errorf("porcentaje fuera de rango (0 a 100): %s", c.Porcentaje)
		case -c.Porcentaje.Exponent() > maxDecimales:
			return fmt.Errorf("porcentaje con más de %d decimales: %s", maxDecimales, c.Porcentaje)
		}
		vistas[c.UnidadID] = true
		suma = suma.Add(c.Porcentaje)
	}
	if !suma.Equal(cien) {
		return fmt.Errorf("los coeficientes suman %s %%, tienen que sumar exactamente 100 %%", suma)
	}
	return nil
}

func vigentes(tx api.Tx, r *http.Request, gid uuid.UUID, f fecha.Fecha) (Vigentes, error) {
	filas, err := api.Lista(tx.Q.CoeficientesVigentes(r.Context(), dbq.CoeficientesVigentesParams{GrupoID: gid, Fecha: f}))
	if err != nil {
		return Vigentes{}, err
	}
	suma := decimal.Zero
	for _, c := range filas {
		suma = suma.Add(c.Porcentaje)
	}
	return Vigentes{GrupoID: gid, Fecha: f, Coeficientes: filas, Suma: suma, SumaCorrecta: suma.Equal(cien)}, nil
}

// Rutas cuelga de /api/v1/administraciones/{administracionID}.
func (s *Servicio) Rutas(r chi.Router) {
	r.Get("/consorcios/{consorcioID}/grupos", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		if !ok {
			return
		}
		api.Leer(w, r, s.pool, "consorcio", func(tx api.Tx) ([]dbq.GrupoProrrateo, error) {
			if _, err := tx.Q.ObtenerConsorcio(r.Context(), cid); err != nil {
				return nil, err
			}
			return api.Lista(tx.Q.ListarGrupos(r.Context(), cid))
		})
	})

	r.Post("/consorcios/{consorcioID}/grupos", func(w http.ResponseWriter, r *http.Request) {
		cid, ok := api.ID(w, r, "consorcioID", "consorcio")
		var a altaGrupo
		if !ok || !httpx.Leer(w, r, &a) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusCreated, "grupo de prorrateo", func(tx api.Tx) (dbq.GrupoProrrateo, error) {
			if strings.TrimSpace(a.Nombre) == "" {
				return dbq.GrupoProrrateo{}, api.Invalido("falta el nombre del grupo")
			}
			g, err := tx.Q.CrearGrupo(r.Context(), dbq.CrearGrupoParams{
				ConsorcioID: cid, Nombre: strings.TrimSpace(a.Nombre), Descripcion: a.Descripcion,
			})
			if err == nil {
				tx.Auditar("grupo_creado", map[string]any{"grupo_id": g.ID, "consorcio_id": cid, "nombre": g.Nombre})
			}
			return g, err
		})
	})

	// Coeficientes vigentes en ?fecha=AAAA-MM-DD (por defecto hoy), con la suma.
	r.Get("/grupos/{grupoID}/coeficientes", func(w http.ResponseWriter, r *http.Request) {
		gid, ok := api.ID(w, r, "grupoID", "grupo de prorrateo")
		if !ok {
			return
		}
		f := fecha.Hoy()
		if s := r.URL.Query().Get("fecha"); s != "" {
			p, err := fecha.Parse(s)
			if err != nil {
				httpx.Error(w, http.StatusBadRequest, err.Error())
				return
			}
			f = p
		}
		api.Leer(w, r, s.pool, "grupo de prorrateo", func(tx api.Tx) (Vigentes, error) {
			if _, err := tx.Q.ObtenerGrupo(r.Context(), gid); err != nil {
				return Vigentes{}, err
			}
			return vigentes(tx, r, gid, f)
		})
	})

	// Carga una tabla nueva que rige desde vigente_desde y cierra la anterior.
	r.Put("/grupos/{grupoID}/coeficientes", func(w http.ResponseWriter, r *http.Request) {
		gid, ok := api.ID(w, r, "grupoID", "grupo de prorrateo")
		var t tabla
		if !ok || !httpx.Leer(w, r, &t) {
			return
		}
		api.Escribir(w, r, s.pool, http.StatusOK, "coeficientes", func(tx api.Tx) (Vigentes, error) {
			if t.VigenteDesde.EsCero() {
				return Vigentes{}, api.Invalido("falta vigente_desde")
			}
			if err := ValidarTabla(t.Coeficientes); err != nil {
				return Vigentes{}, api.Invalido(err.Error())
			}
			g, err := tx.Q.ObtenerGrupo(r.Context(), gid)
			if err != nil {
				return Vigentes{}, err
			}
			ultima, err := tx.Q.UltimaVigenciaGrupo(r.Context(), gid)
			if err != nil {
				return Vigentes{}, err
			}
			if !ultima.EsCero() && !t.VigenteDesde.Despues(ultima) {
				return Vigentes{}, api.Conflicto(fmt.Sprintf(
					"ya hay una tabla que rige desde %s; la nueva tiene que regir después", ultima))
			}
			if _, err := tx.Q.CerrarCoeficientes(r.Context(), dbq.CerrarCoeficientesParams{GrupoID: gid, Desde: &t.VigenteDesde}); err != nil {
				return Vigentes{}, err
			}
			for _, c := range t.Coeficientes {
				if err := tx.Q.InsertarCoeficiente(r.Context(), dbq.InsertarCoeficienteParams{
					ConsorcioID: g.ConsorcioID, GrupoID: gid, UnidadID: c.UnidadID,
					Porcentaje: c.Porcentaje, VigenteDesde: t.VigenteDesde,
				}); err != nil {
					return Vigentes{}, err
				}
			}
			tx.Auditar("coeficientes_cargados", map[string]any{
				"grupo_id": gid, "vigente_desde": t.VigenteDesde, "unidades": len(t.Coeficientes)})
			return vigentes(tx, r, gid, t.VigenteDesde)
		})
	})
}
