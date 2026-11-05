// Alta de usuarios desde la línea de comandos (el primer usuario no puede crearse
// por la API porque todavía no hay nadie que inicie sesión).
//
//	usuarios crear --email ana@ejemplo.com --nombre "Ana" [--administracion "Adm. Centro" --rol admin]
//
// La contraseña se pide por teclado sin mostrarla (o se lee de la entrada estándar si
// no es una terminal). Nunca va como argumento: quedaría en el historial y en `ps`.
package main

import (
	"bufio"
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"strings"

	"github.com/jackc/pgx/v5"
	"golang.org/x/term"

	"github.com/ncmartin77/consorcio/plataforma/internal/platform/audit"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/auth"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/config"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/database"
	"github.com/ncmartin77/consorcio/plataforma/internal/platform/dbq"
)

func main() {
	if err := correr(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}

func correr(args []string) error {
	if len(args) == 0 || args[0] != "crear" {
		return errors.New(`uso: usuarios crear --email X --nombre Y [--administracion Z --rol admin|operador|consulta]`)
	}
	fs := flag.NewFlagSet("crear", flag.ContinueOnError)
	email := fs.String("email", "", "email del usuario (obligatorio)")
	nombre := fs.String("nombre", "", "nombre visible (obligatorio)")
	adm := fs.String("administracion", "", "crea esta administración y le da acceso al usuario")
	rol := fs.String("rol", "admin", "rol en la administración: admin, operador o consulta")
	if err := fs.Parse(args[1:]); err != nil {
		return err
	}
	*email, *nombre, *adm = strings.TrimSpace(*email), strings.TrimSpace(*nombre), strings.TrimSpace(*adm)
	if *email == "" || *nombre == "" || !strings.Contains(*email, "@") {
		return errors.New("faltan --email o --nombre")
	}
	switch *rol {
	case "admin", "operador", "consulta":
	default:
		return fmt.Errorf("rol inválido: %s", *rol)
	}

	password, err := leerPassword()
	if err != nil {
		return err
	}
	hash, err := auth.HashPassword(password)
	if err != nil {
		return err
	}

	cfg, err := config.Cargar()
	if err != nil {
		return err
	}
	ctx := context.Background()
	pool, err := database.Conectar(ctx, cfg.DatabaseURL)
	if err != nil {
		return err
	}
	defer pool.Close()

	return pgx.BeginFunc(ctx, pool, func(tx pgx.Tx) error {
		q := dbq.New(tx)
		uid, err := q.CrearUsuario(ctx, dbq.CrearUsuarioParams{Email: *email, Nombre: *nombre, PasswordHash: &hash})
		if err != nil {
			return fmt.Errorf("crear usuario (¿el email ya existe?): %w", err)
		}
		audit.Registrar(ctx, q, audit.Evento{UsuarioID: &uid, Accion: "usuario_creado",
			Detalle: map[string]any{"email": strings.ToLower(*email), "origen": "cli"}})
		fmt.Printf("Usuario creado: %s (%s)\n", strings.ToLower(*email), uid)
		if *adm == "" {
			return nil
		}
		aid, err := q.CrearAdministracion(ctx, dbq.CrearAdministracionParams{Nombre: *adm})
		if err != nil {
			return err
		}
		if err := q.CrearMembresia(ctx, dbq.CrearMembresiaParams{UsuarioID: uid, AdministracionID: aid, Rol: *rol}); err != nil {
			return err
		}
		audit.Registrar(ctx, q, audit.Evento{AdministracionID: &aid, UsuarioID: &uid, Accion: "administracion_creada",
			Detalle: map[string]any{"nombre": *adm, "rol": *rol, "origen": "cli"}})
		fmt.Printf("Administración creada: %s (%s), rol %s\n", *adm, aid, *rol)
		return nil
	})
}

func leerPassword() (string, error) {
	fd := int(os.Stdin.Fd())
	if !term.IsTerminal(fd) {
		linea, err := bufio.NewReader(os.Stdin).ReadString('\n')
		if err != nil && linea == "" {
			return "", errors.New("no se pudo leer la contraseña de la entrada estándar")
		}
		return strings.TrimRight(linea, "\r\n"), nil
	}
	fmt.Fprintf(os.Stderr, "Contraseña (mínimo %d caracteres): ", auth.LargoMinimoPassword)
	p1, err := term.ReadPassword(fd)
	fmt.Fprintln(os.Stderr)
	if err != nil {
		return "", err
	}
	fmt.Fprint(os.Stderr, "Repetir contraseña: ")
	p2, err := term.ReadPassword(fd)
	fmt.Fprintln(os.Stderr)
	if err != nil {
		return "", err
	}
	if string(p1) != string(p2) {
		return "", errors.New("las contraseñas no coinciden")
	}
	return string(p1), nil
}
