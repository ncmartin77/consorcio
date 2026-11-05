// Package config lee la configuración desde variables de entorno.
package config

import (
	"fmt"
	"os"
)

type Config struct {
	Entorno     string // local | pruebas | produccion
	DireccionHTTP string
	// DatabaseURL conecta con el rol de la aplicación (consorcios_app): sin BYPASSRLS
	// ni propiedad de tablas, así RLS se aplica siempre.
	DatabaseURL string
	// DatabaseURLOwner solo lo usa cmd/migrate (rol dueño del esquema).
	DatabaseURLOwner string
}

func Cargar() (Config, error) {
	c := Config{
		Entorno:          valor("APP_ENV", "local"),
		DireccionHTTP:    valor("HTTP_ADDR", ":8080"),
		DatabaseURL:      os.Getenv("DATABASE_URL"),
		DatabaseURLOwner: os.Getenv("DATABASE_URL_OWNER"),
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
