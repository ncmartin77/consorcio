package auth

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"

	"golang.org/x/crypto/argon2"
)

// Parámetros Argon2id (mínimo recomendado por OWASP: 19 MiB, 2 pasadas, 1 hilo).
const (
	argonMemoria = 19 * 1024
	argonTiempo  = 2
	argonHilos   = 1
	argonSal     = 16
	argonLargo   = 32

	LargoMinimoPassword = 12
)

// HashPassword devuelve el hash en formato PHC: $argon2id$v=19$m=...,t=...,p=...$sal$hash
func HashPassword(password string) (string, error) {
	if len([]rune(password)) < LargoMinimoPassword {
		return "", fmt.Errorf("la contraseña debe tener al menos %d caracteres", LargoMinimoPassword)
	}
	sal := make([]byte, argonSal)
	if _, err := rand.Read(sal); err != nil {
		return "", err
	}
	h := argon2.IDKey([]byte(password), sal, argonTiempo, argonMemoria, argonHilos, argonLargo)
	b64 := base64.RawStdEncoding
	return fmt.Sprintf("$argon2id$v=%d$m=%d,t=%d,p=%d$%s$%s",
		argon2.Version, argonMemoria, argonTiempo, argonHilos, b64.EncodeToString(sal), b64.EncodeToString(h)), nil
}

// VerificarPassword compara en tiempo constante. Respeta los parámetros guardados en el
// hash, así se pueden subir los parámetros sin invalidar contraseñas viejas.
func VerificarPassword(password, codificado string) (bool, error) {
	partes := strings.Split(codificado, "$")
	if len(partes) != 6 || partes[1] != "argon2id" {
		return false, errors.New("hash de contraseña con formato desconocido")
	}
	var version int
	if _, err := fmt.Sscanf(partes[2], "v=%d", &version); err != nil || version != argon2.Version {
		return false, errors.New("versión de argon2 no soportada")
	}
	var m, t uint32
	var p uint8
	if _, err := fmt.Sscanf(partes[3], "m=%d,t=%d,p=%d", &m, &t, &p); err != nil {
		return false, err
	}
	b64 := base64.RawStdEncoding
	sal, err := b64.DecodeString(partes[4])
	if err != nil {
		return false, err
	}
	esperado, err := b64.DecodeString(partes[5])
	if err != nil {
		return false, err
	}
	h := argon2.IDKey([]byte(password), sal, t, m, p, uint32(len(esperado)))
	return subtle.ConstantTimeCompare(h, esperado) == 1, nil
}

// hashFicticio se usa cuando el email no existe, para que la respuesta tarde lo mismo
// y no revele qué emails están registrados.
var hashFicticio, _ = HashPassword("contraseña-ficticia-para-igualar-tiempos")
