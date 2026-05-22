# Estado y Flujos Frontend

## Objetivo

Definir como se administra el estado y como se narran los flujos del frontend usando el principio entrada -> proceso -> salida.

## Regla base

El estado vive donde se entiende.

- estado local si solo lo usa un componente
- estado de pantalla si coordina varias piezas de la misma vista
- estado compartido si varias pantallas o capacidades lo necesitan realmente

## Entrada -> proceso -> salida

### Interaccion de usuario

```text
Entrada: click, submit, keypress, cambio de input
Proceso: validacion, transformacion, decision, llamada a servicio
Salida: render, mensaje de error, actualizacion visual, evento emitido
```

### Carga inicial

```text
Entrada: montaje de pantalla o inicializacion
Proceso: fetch, adaptacion de respuesta, normalizacion de datos
Salida: vista poblada, placeholders, mensaje de error o estado vacio
```

### Tiempo real

```text
Entrada: mensaje de WebSocket o evento SSE
Proceso: parseo, clasificacion, actualizacion del contexto correspondiente
Salida: nuevo mensaje, cambio de estado, alerta o refresco parcial
```

## Reglas para estado local

Usar estado local cuando el dato:

- pertenece a una sola interaccion
- no afecta a otras pantallas
- no necesita persistirse fuera del componente o pantalla

## Reglas para estado compartido

Subir o compartir estado solo cuando:

- varias piezas dependen de la misma fuente de verdad
- la navegacion necesita preservarlo
- el costo de duplicarlo produce inconsistencias

## Reglas para servicios y adaptadores

El flujo recomendado es:

```text
Componente o pantalla -> servicio o adapter -> backend -> servicio o adapter -> pantalla o componente
```

No es recomendable:

- hacer fetch desde muchas piezas sin contrato comun
- mezclar parseo de respuesta y render en el mismo bloque si se repite
- esconder decisiones de estado en utilidades globales no documentadas

## Ejemplo de chat

```text
Entrada: usuario envia mensaje
Proceso: validar texto, enviar por socket, marcar estado de envio, escuchar respuesta
Salida: mensaje renderizado, estado online, error visible o respuesta en stream
```

## Ejemplo de panel admin

```text
Entrada: admin crea baneo o cambia un limite
Proceso: validar formulario, llamar API admin, refrescar resumen y listas
Salida: tabla actualizada, confirmacion visible, evento de seguridad reflejado
```

## Criterios de salud del flujo

- el punto de entrada debe ser identificable rapido
- el proceso no debe mezclar demasiadas responsabilidades
- la salida debe ser observable en UI o en contrato de evento
- el flujo debe ser testeable sin depender de magia del framework
