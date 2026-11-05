// Pruebas de aislamiento entre administraciones (criterio de aceptación del MVP).
// Necesitan la base de deploy/compose.yaml con las migraciones aplicadas:
//
//	make test
package tests

import (
	"context"
	"os"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/database"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
)

func conectar(t *testing.T, variable string) *pgxpool.Pool {
	t.Helper()
	url := os.Getenv(variable)
	if url == "" {
		t.Skipf("%s no configurada", variable)
	}
	pool, err := database.Conectar(context.Background(), url)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	return pool
}

// Arma dos administraciones con un consorcio cada una, usando el rol dueño.
func sembrar(t *testing.T, owner *pgxpool.Pool) (a, b uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	a, b = uuid.New(), uuid.New()
	// Una sentencia por Exec: con parámetros, Postgres no acepta varias juntas.
	for _, q := range []string{
		`INSERT INTO administraciones (id, nombre) VALUES ($1, 'Prueba A'), ($2, 'Prueba B')`,
		`INSERT INTO consorcios (administracion_id, nombre) VALUES ($1, 'Consorcio de A'), ($2, 'Consorcio de B')`,
	} {
		if _, err := owner.Exec(ctx, q, a, b); err != nil {
			t.Fatal(err)
		}
	}
	t.Cleanup(func() {
		owner.Exec(ctx, `DELETE FROM consorcios WHERE administracion_id IN ($1, $2)`, a, b)
		owner.Exec(ctx, `DELETE FROM administraciones WHERE id IN ($1, $2)`, a, b)
	})
	return a, b
}

func TestAislamientoConsorcios(t *testing.T) {
	owner := conectar(t, "DATABASE_URL_OWNER")
	app := conectar(t, "DATABASE_URL")
	ctx := context.Background()
	a, b := sembrar(t, owner)

	t.Run("cada administración ve solo lo suyo", func(t *testing.T) {
		for _, admin := range []uuid.UUID{a, b} {
			err := database.EnTenant(ctx, app, admin, func(tx pgx.Tx) error {
				lista, err := dbq.New(tx).ListarConsorcios(ctx)
				if err != nil {
					return err
				}
				if len(lista) != 1 || lista[0].AdministracionID != admin {
					t.Errorf("administración %s ve %d consorcios: %+v", admin, len(lista), lista)
				}
				return nil
			})
			if err != nil {
				t.Fatal(err)
			}
		}
	})

	t.Run("sin contexto de tenant no se ve nada", func(t *testing.T) {
		var n int
		if err := app.QueryRow(ctx, "SELECT count(*) FROM consorcios").Scan(&n); err != nil {
			t.Fatal(err)
		}
		if n != 0 {
			t.Errorf("sin tenant se ven %d consorcios", n)
		}
	})

	t.Run("no se puede escribir en otra administración", func(t *testing.T) {
		err := database.EnTenant(ctx, app, a, func(tx pgx.Tx) error {
			_, err := tx.Exec(ctx, "INSERT INTO consorcios (administracion_id, nombre) VALUES ($1, 'intruso')", b)
			return err
		})
		if err == nil {
			t.Error("A pudo insertar un consorcio en B")
		}
		err = database.EnTenant(ctx, app, a, func(tx pgx.Tx) error {
			tag, err := tx.Exec(ctx, "UPDATE consorcios SET nombre = 'pisado' WHERE administracion_id = $1", b)
			if err == nil && tag.RowsAffected() != 0 {
				t.Errorf("A modificó %d consorcios de B", tag.RowsAffected())
			}
			return err
		})
		if err != nil {
			t.Fatal(err)
		}
	})

	t.Run("el contexto no se filtra entre transacciones del pool", func(t *testing.T) {
		if err := database.EnTenant(ctx, app, a, func(pgx.Tx) error { return nil }); err != nil {
			t.Fatal(err)
		}
		var v *string
		if err := app.QueryRow(ctx, "SELECT nullif(current_setting('app.administracion_id', true), '')").Scan(&v); err != nil {
			t.Fatal(err)
		}
		if v != nil {
			t.Errorf("quedó app.administracion_id=%s fuera de la transacción", *v)
		}
	})

	t.Run("el rol de la aplicación no saltea RLS", func(t *testing.T) {
		var super, bypass bool
		err := app.QueryRow(ctx, "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user").Scan(&super, &bypass)
		if err != nil {
			t.Fatal(err)
		}
		if super || bypass {
			t.Errorf("rol de la aplicación con superuser=%v bypassrls=%v", super, bypass)
		}
	})
}
