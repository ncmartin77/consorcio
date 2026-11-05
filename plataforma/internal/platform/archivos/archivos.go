// Package archivos guarda y lee archivos (comprobantes, adjuntos, PDFs) en un
// almacenamiento compatible con S3: SeaweedFS en local, Supabase Storage o MinIO.
//
// Aislamiento: toda clave queda bajo el prefijo de su administración
// (adm/<administracion_id>/...). Los métodos reciben el ID de la administración
// y nunca una clave completa, así un handler no puede leer archivos de otro tenant.
package archivos

import (
	"context"
	"errors"
	"fmt"
	"io"
	"regexp"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/aws/smithy-go"
	"github.com/google/uuid"
)

// Config del almacenamiento. Supabase: Endpoint = https://<ref>.supabase.co/storage/v1/s3,
// Region = la del proyecto, claves de Storage → S3 Connection.
type Config struct {
	Endpoint  string
	Region    string
	Bucket    string
	AccessKey string
	SecretKey string
}

var ErrNoExiste = errors.New("archivo inexistente")

type Almacen struct {
	cli    *s3.Client
	bucket string
}

func Nuevo(c Config) (*Almacen, error) {
	if c.Endpoint == "" || c.Bucket == "" || c.AccessKey == "" || c.SecretKey == "" {
		return nil, errors.New("archivos: faltan S3_ENDPOINT, S3_BUCKET o las claves S3")
	}
	if c.Region == "" {
		c.Region = "us-east-1"
	}
	cli := s3.New(s3.Options{
		BaseEndpoint: aws.String(c.Endpoint),
		Region:       c.Region,
		Credentials:  credentials.NewStaticCredentialsProvider(c.AccessKey, c.SecretKey, ""),
		UsePathStyle: true,
		// Supabase y SeaweedFS no aceptan los checksums CRC que el SDK agrega por defecto.
		RequestChecksumCalculation: aws.RequestChecksumCalculationWhenRequired,
		ResponseChecksumValidation: aws.ResponseChecksumValidationWhenRequired,
	})
	return &Almacen{cli: cli, bucket: c.Bucket}, nil
}

// AsegurarBucket crea el bucket si no existe. Solo para desarrollo local: en Supabase
// el bucket (privado) se crea desde el panel.
func (a *Almacen) AsegurarBucket(ctx context.Context) error {
	if _, err := a.cli.HeadBucket(ctx, &s3.HeadBucketInput{Bucket: &a.bucket}); err == nil {
		return nil
	}
	_, err := a.cli.CreateBucket(ctx, &s3.CreateBucketInput{Bucket: &a.bucket})
	var ya *types.BucketAlreadyOwnedByYou
	if errors.As(err, &ya) {
		return nil
	}
	return err
}

// Cada parte de la ruta: letras, números, punto, guion y guion bajo; sin "." ni "..".
var parteValida = regexp.MustCompile(`^[A-Za-z0-9._-]{1,128}$`)

// Clave arma la clave completa dentro del prefijo de la administración.
func Clave(administracionID uuid.UUID, ruta ...string) (string, error) {
	if administracionID == uuid.Nil {
		return "", errors.New("archivos: administración vacía")
	}
	if len(ruta) == 0 {
		return "", errors.New("archivos: ruta vacía")
	}
	for _, p := range ruta {
		if !parteValida.MatchString(p) || p == "." || p == ".." {
			return "", fmt.Errorf("archivos: parte de ruta inválida %q", p)
		}
	}
	return "adm/" + administracionID.String() + "/" + strings.Join(ruta, "/"), nil
}

type Info struct {
	Clave       string
	Tamano      int64
	ContentType string
}

// Subir guarda el contenido (tamaño conocido) y reemplaza si ya existía.
func (a *Almacen) Subir(ctx context.Context, adm uuid.UUID, ruta []string, contentType string, r io.Reader, tamano int64) (Info, error) {
	clave, err := Clave(adm, ruta...)
	if err != nil {
		return Info{}, err
	}
	if contentType == "" {
		contentType = "application/octet-stream"
	}
	_, err = a.cli.PutObject(ctx, &s3.PutObjectInput{
		Bucket:        &a.bucket,
		Key:           &clave,
		Body:          r,
		ContentLength: aws.Int64(tamano),
		ContentType:   &contentType,
	})
	if err != nil {
		return Info{}, fmt.Errorf("archivos: subir %s: %w", clave, err)
	}
	return Info{Clave: clave, Tamano: tamano, ContentType: contentType}, nil
}

// Bajar devuelve el contenido; quien llama cierra el ReadCloser.
func (a *Almacen) Bajar(ctx context.Context, adm uuid.UUID, ruta ...string) (io.ReadCloser, Info, error) {
	clave, err := Clave(adm, ruta...)
	if err != nil {
		return nil, Info{}, err
	}
	out, err := a.cli.GetObject(ctx, &s3.GetObjectInput{Bucket: &a.bucket, Key: &clave})
	if err != nil {
		if noExiste(err) {
			return nil, Info{}, ErrNoExiste
		}
		return nil, Info{}, fmt.Errorf("archivos: bajar %s: %w", clave, err)
	}
	return out.Body, Info{Clave: clave, Tamano: aws.ToInt64(out.ContentLength), ContentType: aws.ToString(out.ContentType)}, nil
}

func (a *Almacen) Existe(ctx context.Context, adm uuid.UUID, ruta ...string) (bool, error) {
	clave, err := Clave(adm, ruta...)
	if err != nil {
		return false, err
	}
	_, err = a.cli.HeadObject(ctx, &s3.HeadObjectInput{Bucket: &a.bucket, Key: &clave})
	if err == nil {
		return true, nil
	}
	if noExiste(err) {
		return false, nil
	}
	return false, fmt.Errorf("archivos: consultar %s: %w", clave, err)
}

// Borrar no falla si el archivo no existe.
func (a *Almacen) Borrar(ctx context.Context, adm uuid.UUID, ruta ...string) error {
	clave, err := Clave(adm, ruta...)
	if err != nil {
		return err
	}
	if _, err := a.cli.DeleteObject(ctx, &s3.DeleteObjectInput{Bucket: &a.bucket, Key: &clave}); err != nil && !noExiste(err) {
		return fmt.Errorf("archivos: borrar %s: %w", clave, err)
	}
	return nil
}

func noExiste(err error) bool {
	var nsk *types.NoSuchKey
	var nf *types.NotFound
	if errors.As(err, &nsk) || errors.As(err, &nf) {
		return true
	}
	var api smithy.APIError
	if errors.As(err, &api) {
		switch api.ErrorCode() {
		case "NoSuchKey", "NotFound", "404":
			return true
		}
	}
	return false
}
