# Arquitectura Frontend

## Estructura base

La estructura exacta puede cambiar segun el stack, pero la separacion conceptual debe mantenerse.

```text
frontend/
├── README.md
├── front_filosofia_general.md
├── front_arquitectura.md
├── front_componentes.md
├── front_estado_y_flujos.md
├── front_documentacion_y_composicion.md
├── screens/
├── components/
├── services/
├── state/
├── styles/
└── bootstrap/
```

## Responsabilidad por capa

### screens

- componen la experiencia de una capacidad completa
- orquestan componentes hijos
- conectan eventos de interfaz con servicios o stores
- no deberian convertirse en componentes gigantes

### components

- encapsulan una sola funcion visual o interactiva
- reciben entradas claras
- procesan comportamiento local
- producen una salida visual o un evento entendible

### services

- encapsulan llamadas HTTP, WebSocket o integraciones del cliente
- ocultan detalles de transporte al resto del frontend
- no renderizan ni tocan DOM directamente

### state

- administra estado compartido solo cuando hay una necesidad real
- no debe reemplazar al estado local por costumbre
- debe exponer contratos claros de lectura y actualizacion

### styles

- resuelven presentacion
- no deben ocultar reglas de negocio
- deben acompañar la composicion, no gobernarla

### bootstrap

- inicializa la aplicacion o pantalla
- conecta dependencias base
- registra rutas, stores o servicios comunes segun el stack

## Flujo canonico

Todo flujo del frontend debe poder mapearse asi:

```text
Entrada -> Proceso -> Salida
```

Ejemplos:

### Formulario

```text
Input del usuario -> Validacion y transformacion -> Render de errores o submit exitoso
```

### Peticion HTTP

```text
Click o carga inicial -> Llamada al servicio + adaptacion de datos -> Estado actualizado y nueva vista
```

### WebSocket

```text
Mensaje entrante -> Parseo y clasificacion -> Actualizacion del componente o la pantalla
```

## Mapeo por stack

### Vanilla

- `screen controller` como punto de composicion
- modulos pequenos para servicios
- referencias a DOM explicitas y nombradas

### React

- `page` o `route component` como pantalla
- componentes pequenos por funcion
- hooks o servicios para acceso a APIs y sockets

### Angular

- componente contenedor como pantalla
- componentes presentacionales para piezas aisladas
- servicios inyectables para transporte y estado compartido

## Aplicacion al repo actual

La base actual del proyecto ya se puede leer con esta arquitectura:

- `index.html` actua como pantalla de chat
- `engrams.html` actua como pantalla de identidades
- `routes.py` actua como adaptador web para servir esas pantallas

La evolucion recomendada no es cambiar de stack ahora, sino formalizar estas fronteras y extenderlas con nuevas pantallas, por ejemplo una pantalla administrativa local.
