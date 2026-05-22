# Filosofia General Frontend

## Proposito

El frontend debe poder crecer sin convertirse en una mezcla opaca de templates, estados, handlers y llamadas al backend. La regla central es simple: cada pieza visual debe recibir una entrada clara, ejecutar un proceso entendible y producir una salida verificable.

## Principios rectores

1. Todo flujo visible debe seguir entrada -> proceso -> salida.
2. Cada componente existe para una sola funcion significativa.
3. El contexto de un componente debe vivir lo mas cerca posible de ese componente.
4. Los nombres deben ser reconocibles, especificos y auditables.
5. La composicion debe ser explicita; no se debe esconder comportamiento importante en side effects opacos.
6. El framework es una herramienta, no la arquitectura.
7. La documentacion del frontend es parte del contrato tecnico.

## Decisiones de alto nivel

### Pantalla como frontera de composicion

La pantalla es la unidad principal de composicion del frontend. Una pantalla puede combinar multiples componentes, pero debe expresar una sola capacidad reconocible del sistema.

Ejemplos:

- chat principal
- gestion de identidades
- panel admin de seguridad

### Componente como unidad de responsabilidad unica

Un componente no debe resolver varias intenciones de negocio al mismo tiempo. Si una pieza renderiza, valida, persiste, escucha sockets y administra una tabla entera sin fronteras claras, ya no es un componente sano.

### Entrada -> proceso -> salida como contrato universal

Todo comportamiento de frontend debe poder narrarse asi:

- entrada: evento, props, datos remotos, estado compartido
- proceso: validacion, transformacion, decision, llamada a servicio
- salida: render, evento emitido, estado actualizado, feedback al usuario

### Contexto local primero

El estado local debe quedarse local mientras no exista una razon real para compartirlo. Subir estado a una capa superior o a un store global solo se justifica cuando multiples piezas lo necesitan de verdad.

### Framework agnostico por diseno

Estas reglas aplican igual si la implementacion se hace en:

- vanilla JavaScript
- React
- Angular
- cualquier stack equivalente

Lo que cambia es la sintaxis. La responsabilidad, la composicion y los contratos no deberian cambiar.

## Criterios de calidad

- si un componente no puede explicarse en una frase, probablemente hace demasiado
- si un handler necesita leer media pantalla para entenderse, falta una frontera clara
- si una variable no expresa dominio ni intencion, no es auditable
- si una pantalla depende de multiples globales no declarados, el contexto esta roto
- si una funcionalidad nueva obliga a tocar muchos componentes no relacionados, falta delimitacion

## Resultado esperado

Un frontend basado en esta filosofia debe ser:

- facil de leer para un desarrollador nuevo
- facil de extender sin romper piezas no relacionadas
- consistente aunque cambie el framework
- auditable en nombres, flujos y contratos
- capaz de crecer por pantallas y componentes sin rehacerse desde cero
