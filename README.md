# HRMS · Sistema de Gestión de Recursos Humanos

Sistema web de RRHH para empresas argentinas, inspirado en Freshteam. Está desarrollado en **Python / Django**,
se usa desde cualquier navegador y se puede alojar en un servicio cloud (Render, Railway, Fly.io) o en un servidor propio con Docker.

- Moneda: pesos argentinos (`$ 1.234.567,89`), fechas `dd/mm/aaaa`, zona horaria de Buenos Aires.
- Normativa de referencia: Ley de Contrato de Trabajo 20.744 con las modificaciones de la Ley 27.802 (2026).

## Funcionalidades

| Módulo | Qué incluye |
|---|---|
| **Legajos** | Ficha completa del empleado: datos personales, CUIL validado con dígito verificador, datos laborales, CCT y categoría, obra social, cuenta sueldo (CBU), jefe directo, grupo familiar (familiares a cargo), contactos de emergencia, foto. Alta, edición, baja con motivo (renuncia, despido, art. 241, etc.) y reingreso. Exportación a Excel. |
| **Documentos** | Carga de varios archivos a la vez por legajo (PDF, imágenes, Word, Excel), con categorías (DNI, alta temprana, certificados médicos, contratos, recibos, telegramas…), fecha de vencimiento, aviso de vencimientos y opción de ocultarlos al empleado. Los archivos **no son públicos**: se descargan a través del sistema, verificando permisos. |
| **Salarios** | Historial de ajustes con salario base anterior y nuevo, variación % y respaldo adjunto. **Costos adicionales** (uno o varios, con concepto e importe) que se suman al salario base para obtener el **total con adicionales**; se mantienen automáticamente en los ajustes siguientes. Ajuste por monto o por porcentaje. **Ajuste masivo** (paritarias) por área o convenio, con vista previa antes de confirmar. **Esquema de ajuste por empleado**: frecuencia (mensual, cada N meses o anual), referencia (fecha de ingreso o fecha calendario) y método (IPC del INDEC con rezago y adicional opcional, porcentaje fijo o monto fijo). Pantalla **Próximos ajustes** con último ajuste, próxima fecha, días restantes, salario estimado y aplicación en un clic (individual o por selección). Tabla de **IPC mensual** editable. |
| **Vacaciones y licencias** | Tipos de licencia precargados según la LCT (vacaciones, enfermedad, ART, matrimonio, nacimiento, fallecimiento, examen, maternidad, excedencia, sin goce, etc.), configurables. Cómputo en días corridos o hábiles (descuenta fines de semana y feriados). Saldos de vacaciones generados automáticamente por antigüedad (art. 150: 14/21/28/35 días; art. 153 para ingresos del año) con arrastre opcional (tope de 1/3, art. 164). Control de superposición, tope por evento y tope anual. Avisos de tramo mínimo de 7 días (Ley 27.802) y de preaviso. Flujo de **solicitud → aprobación** por RRHH o el jefe directo, con aviso por email. Calendario mensual de ausencias por área. |
| **Feriados** | Feriados 2026 precargados y **actualización automática semanal** en el servidor (año actual y siguiente) desde ArgentinaDatos, con Nager.Date como respaldo. Los feriados cargados o editados a mano nunca se pisan. Leyenda "Última actualización" en la pantalla de feriados. También: `python manage.py actualizar_feriados [--forzar]` para un cron. |
| **Asistencia** | Inasistencias (justificadas / injustificadas, con goce, con comprobante), llegadas tarde (calcula minutos de demora según el horario del empleado o de la empresa) y horas extras (recargo 50 % / 100 % calculado según día y feriado; pago o banco de horas; aprobación). **Resumen mensual de novedades para liquidación** exportable a Excel. Todos los listados de asistencia y el resumen mensual se pueden **descargar en PDF o imprimir** (con totales). **Resumen por empleado**: detalle de inasistencias, llegadas tarde, horas extras y licencias con motivo, documentación y aprobación, subtotales por tipo y total general (web, PDF e impresión). |
| **Reclutamiento (ATS)** | Búsquedas laborales, candidatos con CV, pipeline tipo kanban por etapas, entrevistas con devolución y puntaje, oferta, y **contratación en un clic** (crea el legajo, el salario de ingreso, copia el CV y arranca el onboarding). **Portal público de empleos** (`/empleos/`) donde los candidatos se postulan con consentimiento según la Ley 25.326. |
| **Onboarding / Offboarding** | Plantillas de checklist con tareas, responsables y plazos relativos (precargadas: ingreso estándar con alta temprana, preocupacional, etc.; egreso con baja en ARCA, certificado art. 80, etc.). Seguimiento de avance y "Mis tareas". |
| **Autogestión** | Cada empleado con usuario ve **su legajo**, sus documentos, sus saldos, pide vacaciones/licencias adjuntando comprobantes y consulta su asistencia. |
| **Mi equipo** | Los jefes directos ven a su equipo, aprueban sus solicitudes y horas extras y ven el calendario del equipo. |
| **Inicio** | Panel con dotación, ingresos/egresos del mes, quién está ausente hoy, aprobaciones pendientes, cumpleaños y aniversarios, próximos feriados, vencimientos de período de prueba, contratos y documentos, anuncios y entrevistas. |
| **Directorio y organigrama** | Directorio con foto y contacto (descarga de vCard) y organigrama generado a partir de los jefes directos. |
| **Anuncios** | Comunicados para toda la empresa o por área, destacados y con vigencia. |
| **Reportes** | Dotación (por área, sede, modalidad, género, convenio), altas/bajas y rotación, edad y antigüedad, ausentismo, llegadas tarde, horas extras, saldos de vacaciones y masa salarial; todos exportables a Excel y con gráficos. |
| **Integridad de datos** | Cada operación se graba en una única transacción: o se guarda completa o no se guarda nada (sin registros a medias si la base falla durante la operación). Los emails de aviso se envían solo cuando la operación quedó grabada. |
| **Barra de estado** | Pie con reloj en tiempo real (hora de Argentina) e indicador de conexión que verifica cada 30 s que el servidor y la base de datos respondan y acepten escrituras: verde (funcionando), amarillo (inestable: verificar los cambios) o rojo (sin conexión: los cambios no se guardan; se bloquea el envío de formularios). |
| **Usuarios, roles y auditoría** | Usuario administrador total y **roles configurables** con nivel de acceso por módulo (sin acceso / ver / ver y editar / administrar). Registro de auditoría de altas, modificaciones, bajas, aprobaciones e inicios de sesión. |

### Roles y permisos

Cada rol define un nivel por módulo; si un usuario tiene varios roles, se toma el nivel más alto.

- **Ver**: consultar. **Ver y editar**: altas y modificaciones. **Administrar**: además eliminar y aprobar.
- Roles precargados (editables): Administrador RRHH, Analista RRHH, Líder de equipo, Reclutador, Liquidación de sueldos, Empleado.
- Sin importar el rol: todo usuario vinculado a un legajo accede a su autogestión, y los jefes directos aprueban las solicitudes de su equipo.
- El **administrador total** (superusuario) tiene acceso a todo y es el único que puede modificar a otros administradores totales.

## Probarlo desde el navegador (iPad, tablet o cualquier PC) con GitHub Codespaces

Sin instalar nada:

1. Abrí el repositorio en GitHub desde el navegador.
2. **Code → pestaña Codespaces → Create codespace on main**.
3. Esperá unos minutos: se instalan las dependencias y se cargan los datos demo automáticamente.
4. Cuando aparezca el aviso del puerto **8000**, tocá **Open in Browser** (o abrí la pestaña *Ports* y el ícono del globo en el puerto 8000).
5. Ingresá con `admin` / `admin1234` o con los usuarios demo `rrhh`, `jefe`, `empleado` (clave `Demo1234!`).

Si el servidor no está corriendo, en la terminal del Codespace ejecutá `python manage.py runserver 0.0.0.0:8000`.
Cuando termines, detené el Codespace (menú *Codespaces → Stop*) para no consumir la cuota mensual gratuita.

## Probarlo en tu computadora

Requisitos: Python 3.11 o superior.

```bash
python -m venv .venv
source .venv/bin/activate          # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser   # crea tu usuario administrador
python manage.py inicializar       # roles, tipos de licencia, feriados y plantillas
python manage.py datos_demo        # OPCIONAL: empleados y movimientos ficticios para probar
python manage.py runserver
```

Abrí http://127.0.0.1:8000. Con los datos demo hay tres usuarios de prueba (contraseña `Demo1234!`):
`rrhh` (Analista RRHH), `jefe` (Líder de equipo, con colaboradores a cargo) y `empleado` (solo autogestión).

Tests automáticos: `python manage.py test tests`

## Publicarlo en internet

La configuración se hace con variables de entorno (ver `.env.example`). Lo importante:

- `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY` (clave larga y aleatoria) y `DJANGO_ALLOWED_HOSTS` con tu dominio.
- `DATABASE_URL` apuntando a **PostgreSQL** (SQLite sirve solo para pruebas).
- `DJANGO_MEDIA_ROOT` en un **disco persistente**: ahí se guardan los documentos, fotos y CVs. Si el hosting borra el disco en cada despliegue, se pierden los archivos.
- `HRMS_ADMIN_USER` y `HRMS_ADMIN_PASSWORD` para que se cree el administrador inicial.

### Opción A: Render (la más simple)

1. Subí este repositorio a GitHub (ya está).
2. En [render.com](https://render.com): **New + → Blueprint** y elegí el repositorio. Usa `render.yaml`, que crea el servicio web, la base PostgreSQL y un disco de 5 GB para los archivos.
3. Completá `HRMS_ADMIN_USER` y `HRMS_ADMIN_PASSWORD` cuando lo pida y desplegá.

El disco persistente de Render requiere un plan pago. Revisá los planes y precios vigentes en Render antes de crear los servicios; los nombres de plan de `render.yaml` pueden cambiar.

### Opción B: servidor propio o VPS con Docker

```bash
cp .env.example .env    # completar valores
docker compose up -d --build
```

Levanta PostgreSQL y la aplicación en el puerto 8000, con volúmenes persistentes para la base y los archivos. Delante conviene poner un proxy con HTTPS (Nginx, Caddy o Cloudflare Tunnel).

### Opción C: otros PaaS (Railway, Fly.io, Heroku)

El `Procfile` y el `Dockerfile` sirven para la mayoría. Configurá las variables de entorno, agregá una base PostgreSQL y un volumen persistente montado en `DJANGO_MEDIA_ROOT`.

### Backups

Hacé copias periódicas de la base PostgreSQL (`pg_dump`) **y** de la carpeta de archivos (`DJANGO_MEDIA_ROOT`).

## Notas legales y de configuración

- Las reglas legales están en `apps/licencias/lct.py` y en los tipos de licencia (editables desde *Configuración → Tipos de licencia*). Muchos convenios colectivos dan más días que la LCT (por ejemplo, por nacimiento); ajustalos según el CCT de tu empresa.
- Los feriados 2026 se cargaron desde el calendario oficial difundido para ese año. Verificalos en [argentina.gob.ar/interior/feriados](https://www.argentina.gob.ar/interior/feriados), porque el Poder Ejecutivo puede agregar o mover fechas.
- El sistema **no liquida sueldos**: registra las novedades (licencias, ausencias, tardanzas y horas extras) y las exporta para el liquidador o el sistema de liquidación.
- El sistema guarda datos personales y sensibles (salud, documentos). Usá HTTPS, contraseñas fuertes y asigná a cada persona solo los roles que necesita.

## Estructura del proyecto

```
config/            settings, urls, wsgi
apps/core/         usuarios, roles/permisos, configuración, auditoría, panel de inicio, archivos protegidos
apps/empleados/    legajos, documentos, salarios, áreas, puestos, sedes, directorio, organigrama
apps/licencias/    tipos, saldos, solicitudes y aprobaciones, calendario, feriados, reglas LCT
apps/asistencia/   inasistencias, llegadas tarde, horas extras, resumen mensual
apps/reclutamiento/búsquedas, candidatos, postulaciones, entrevistas, portal público
apps/onboarding/   plantillas y checklists de ingreso/egreso
apps/anuncios/     comunicados
apps/reportes/     reportes y exportación a Excel
templates/, static/ interfaz (Bootstrap 5 servido localmente, sin depender de CDNs)
tests/             tests automáticos
```
