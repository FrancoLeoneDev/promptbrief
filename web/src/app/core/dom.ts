/**
 * Los dos accesos al `event.target` que necesitan los formularios.
 *
 * Están acá y no repetidos con un `$any(...)` en cada plantilla: el cast vive en un solo
 * lugar tipado y las plantillas quedan legibles.
 */

export function textOf(event: Event): string {
  return (event.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement).value;
}

export function checkedOf(event: Event): boolean {
  return (event.target as HTMLInputElement).checked;
}
