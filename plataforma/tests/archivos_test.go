package tests

import (
	"bytes"
	"context"
	"errors"
	"io"
	"os"
	"testing"

	"github.com/google/uuid"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/archivos"
)

// Corre contra el S3 que indiquen las variables S3_* (SeaweedFS local con make test,
// Supabase Storage con make test-supabase). Sin S3_ENDPOINT se saltea.
func almacen(t *testing.T) *archivos.Almacen {
	t.Helper()
	if os.Getenv("S3_ENDPOINT") == "" {
		t.Skip("S3_ENDPOINT no definida")
	}
	a, err := archivos.Nuevo(archivos.Config{
		Endpoint:  os.Getenv("S3_ENDPOINT"),
		Region:    os.Getenv("S3_REGION"),
		Bucket:    os.Getenv("S3_BUCKET"),
		AccessKey: os.Getenv("S3_ACCESS_KEY_ID"),
		SecretKey: os.Getenv("S3_SECRET_ACCESS_KEY"),
	})
	if err != nil {
		t.Fatal(err)
	}
	if os.Getenv("S3_CREAR_BUCKET") == "1" {
		if err := a.AsegurarBucket(context.Background()); err != nil {
			t.Fatal(err)
		}
	}
	return a
}

func TestArchivos(t *testing.T) {
	a := almacen(t)
	ctx := context.Background()
	admA, admB := uuid.New(), uuid.New()
	ruta := []string{"pruebas", "comprobante.pdf"}
	contenido := []byte("%PDF-1.4 prueba de la plataforma")
	t.Cleanup(func() { a.Borrar(ctx, admA, ruta...) })

	info, err := a.Subir(ctx, admA, ruta, "application/pdf", bytes.NewReader(contenido), int64(len(contenido)))
	if err != nil {
		t.Fatal(err)
	}
	if info.Clave != "adm/"+admA.String()+"/pruebas/comprobante.pdf" {
		t.Errorf("clave inesperada: %s", info.Clave)
	}

	t.Run("se baja igual que se subió", func(t *testing.T) {
		rc, inf, err := a.Bajar(ctx, admA, ruta...)
		if err != nil {
			t.Fatal(err)
		}
		defer rc.Close()
		leido, _ := io.ReadAll(rc)
		if !bytes.Equal(leido, contenido) {
			t.Errorf("contenido distinto: %q", leido)
		}
		if inf.ContentType != "application/pdf" {
			t.Errorf("content-type %q", inf.ContentType)
		}
	})

	t.Run("otra administración no lo ve", func(t *testing.T) {
		if ok, err := a.Existe(ctx, admB, ruta...); err != nil || ok {
			t.Errorf("admB ve el archivo de admA (ok=%v, err=%v)", ok, err)
		}
		if _, _, err := a.Bajar(ctx, admB, ruta...); !errors.Is(err, archivos.ErrNoExiste) {
			t.Errorf("admB bajó el archivo de admA: %v", err)
		}
	})

	t.Run("rutas que intentan salir del prefijo se rechazan", func(t *testing.T) {
		for _, mala := range [][]string{{".."}, {"..", admB.String()}, {"a/b"}, {""}, {"x y"}} {
			if _, err := archivos.Clave(admA, mala...); err == nil {
				t.Errorf("aceptó la ruta %q", mala)
			}
		}
	})

	t.Run("borrar", func(t *testing.T) {
		if err := a.Borrar(ctx, admA, ruta...); err != nil {
			t.Fatal(err)
		}
		if ok, _ := a.Existe(ctx, admA, ruta...); ok {
			t.Error("sigue existiendo después de borrar")
		}
	})
}
