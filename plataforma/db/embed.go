// Package db embebe las migraciones SQL para que el binario no dependa de archivos sueltos.
package db

import "embed"

//go:embed migrations/*.sql
var Migraciones embed.FS
