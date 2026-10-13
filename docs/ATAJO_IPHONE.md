# Acceso rápido en el iPhone

Hay tres formas, de más simple a más rápida. Puedes usar las tres a la vez.

## 1. Ícono en la pantalla de inicio (app web)
1. Abre `https://TU-SERVIDOR/` en **Safari** (debe ser Safari).
2. Compartir → **Agregar a pantalla de inicio**. Queda como app "Gastos" a pantalla completa.
3. La primera vez te pide el token (`APP_TOKEN`); queda guardado en el teléfono.

## 2. Atajo "Gasto" (Apple Atajos) — registrar sin abrir la app
Crea un atajo nuevo con estas acciones:

1. **Pedir entrada** → tipo *Texto* → "¿Monto?" (acepta `33550-101`).
2. **Pedir entrada** → tipo *Texto* → "¿Descripción?" (opcional).
3. **Obtener contenido de URL** `https://TU-SERVIDOR/api/opciones` con el encabezado `Authorization: Bearer TU_TOKEN`.
4. **Obtener valor del diccionario** → `categorias` → **Elegir de la lista** (esto da el menú de categorías; si la descripción ya existe en tu historial puedes omitir este paso y la app la infiere).
5. **Obtener contenido de URL** `https://TU-SERVIDOR/api/rapido`
   - Método: **POST**, Cuerpo de la solicitud: **JSON**
   - Encabezado: `Authorization: Bearer TU_TOKEN`
   - Campos: `monto` (Texto), `descripcion` (Texto), `categoria` (Texto, de la lista). Opcionales: `tarjeta`, `tipo` (`Personal`/`Compartido`), `fecha` (`AAAA-MM-DD`).
6. **Obtener valor del diccionario** → `mensaje` → **Mostrar notificación**.
   Ejemplo: `Jumbo $74.346 · tu parte $44.608 · Súper: quedan $6.131 de $150.000`

Si no envías `categoria`/`tarjeta`/`tipo`, la app copia los del último gasto con la misma descripción.

### Cómo dispararlo rápido
- **Pantalla de inicio**: en el atajo → ⓘ → *Agregar a pantalla de inicio*.
- **Botón de Acción** (iPhone 15 Pro o posterior): Ajustes → Botón de Acción → Atajo → "Gasto".
- **Tocar atrás**: Ajustes → Accesibilidad → Tocar → Tocar atrás → Atajo "Gasto".
- **Siri**: di "Gasto" (el nombre del atajo).
- **Centro de control** y **pantalla bloqueada**: se pueden añadir controles de Atajos.

### Opcional: automatizar con Apple Pay
En Atajos → Automatización → *Transacción* (si tu iOS/tarjeta la ofrece) puedes llamar al mismo `/api/rapido` con el monto y comercio de la compra. Depende de que tu banco soporte Wallet; pruébalo.

## Seguridad
- Usa siempre HTTPS (o una red privada como Tailscale) y un `APP_TOKEN` largo.
- El token viaja en el encabezado `Authorization`; evita ponerlo en la URL.
