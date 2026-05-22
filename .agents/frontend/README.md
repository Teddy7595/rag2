# Frontend Standar

Este directorio define una filosofia de frontend reusable inspirada en `.agents`, pero pensada para interfaces, pantallas, componentes y flujos del lado cliente.

El objetivo no es atar el proyecto a un framework concreto, sino fijar reglas que permitan construir frontend escalable, auditable y entendible tanto en vanilla como en Angular o React.

## Objetivos del estandar

- disenar frontend por pantallas y capacidades, no por archivos sueltos
- obligar a que todo flujo siga el principio entrada -> proceso -> salida
- mantener responsabilidad unica real por componente
- usar nombres auditables y entendibles para variables, estados y handlers
- preservar contexto y funcionalidad local en cada componente
- documentar composicion, funcionamiento y puntos de extension del frontend
- permitir cambiar de stack sin perder reglas de arquitectura

## Documentos incluidos

- [front_filosofia_general.md](./front_filosofia_general.md)
- [front_arquitectura.md](./front_arquitectura.md)
- [front_componentes.md](./front_componentes.md)
- [front_estado_y_flujos.md](./front_estado_y_flujos.md)
- [front_documentacion_y_composicion.md](./front_documentacion_y_composicion.md)

## Contrato minimo del frontend estandar

- debe existir un `README.md` del frontend
- deben existir documentos `front_*.md` que definan filosofia, arquitectura y composicion
- cada pantalla debe poder explicarse por si misma
- cada componente debe tener una sola responsabilidad clara
- cada flujo relevante debe poder narrarse como entrada -> proceso -> salida
- los nombres de variables y estados deben ser reconocibles para quien audita el codigo
- la documentacion debe seguir siendo valida aunque cambie el framework

## Base actual del repo

El proyecto actual usa frontend servido por FastAPI con plantillas Jinja y JavaScript inline:

- `index.html` como pantalla de chat
- `engrams.html` como pantalla de identidades

Ese punto de partida es valido. Este estandar no obliga a migrar a SPA ni a otro stack. Solo exige que, sea cual sea el stack, la composicion y los contratos sean claros.

## Uso recomendado

Lee primero `front_filosofia_general.md` y `front_arquitectura.md`. Luego usa los demas documentos como contratos de composicion, estado y documentacion del frontend.
