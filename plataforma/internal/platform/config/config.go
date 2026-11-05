// Package config lee la configuración desde variables de entorno.
package config

import (
	"fmt"
	"os"
)

type Config struct {
	Entorno       string // local | pruebas | produccion
	DireccionHTTP string
	// DatabaseURL conecta con el rol de la aplicación (consorcios_app): sin BYPASSRLS
	// ni propiedad de tablas, así RLS se aplica siempre.
	DatabaseURL string
	// DatabaseURLOwner solo lo usa cmd/migrate (rol dueño del esquema).
	DatabaseURLOwner string
	// Almacenamiento S3 (SeaweedFS local, Supabase Storage o MinIO).
	S3Endpoint, S3Region, S3Bucket, S3AccessKey, S3SecretKey string
}

func Cargar() (Config, error) {
	c := Config{
		Entorno:          valor("APP_ENV", "local"),
		DireccionHTTP:    valor("HTTP_ADDR", ":8080"),
		DatabaseURL:      os.Getenv("DATABASE_URL"),
		DatabaseURLOwner: os.Getenv("DATABASE_URL_OWNER"),
		S3Endpoint:       os.Getenv("S3_ENDPOINT"),
		S3Region:         valor("S3_REGION", "us-east-1"),
		S3Bucket:         valor("S3_BUCKET", "plataforma"),
		S3AccessKey:      os.Getenv("S3_ACCESS_KEY_ID"),
		S3SecretKey:      os.Getenv("S3_SECRET_ACCESS_KEY"),
	}
	switch c.Entorno {
	case "local", "pruebas", "produccion":
	default:
		return c, fmt.Errorf("APP_ENV inválido: %q", c.Entorno)
	}
	return c, nil
}

func valor(clave, porDefecto string) string {
	if v := os.Getenv(clave); v != "" {
		return v
	}
	return porDefecto
}
