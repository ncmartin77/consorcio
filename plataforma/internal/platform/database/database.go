// Package database maneja el pool de PostgreSQL, las migraciones y el contexto
// multi-tenant que usan las políticas RLS.
package database

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/jackc/pgx/v5/stdlib"
	"github.com/pressly/goose/v3"

	"github.com/ncmartin77/consorcio/plataforma/db"
)


func Conectar(ctx context.Context, url string) (*pgxpool.Pool, error) {
	if url == "" {
		return nil, errors.New("DATABASE_URL no configurado")
	}
	pool, err := pgxpool.New(ctx, url)
	if err != nil {
		return nil, err
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("no se pudo conectar a PostgreSQL: %w", err)
	}
	return pool, nil
}

// Migrar aplica las migraciones pendientes. Se corre con el rol dueño del esquema.
func Migrar(ctx context.Context, url string) error {
	cfg, err := pgx.ParseConfig(url)
	if err != nil {
		return err
	}
	sqlDB := stdlib.OpenDB(*cfg)
	defer sqlDB.Close()

	goose.SetBaseFS(db.Migraciones)
	if err := goose.SetDialect("postgres"); err != nil {
		return err
	}
	return goose.UpContext(ctx, sqlDB, "migrations")
}

// EnTenant ejecuta fn dentro de una transacción con app.administracion_id fijado
// (alcance transaccional: no se filtra a otras conexiones del pool).
// Quien llama debe haber verificado antes la membresía del usuario en esa administración.
func EnTenant(ctx context.Context, pool *pgxpool.Pool, administracionID uuid.UUID, fn func(pgx.Tx) error) error {
	return pgx.BeginFunc(ctx, pool, func(tx pgx.Tx) error {
		if _, err := tx.Exec(ctx, "SELECT set_config('app.administracion_id', $1, true)", administracionID.String()); err != nil {
			return err
		}
		return fn(tx)
	})
}
