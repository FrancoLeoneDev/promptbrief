import { DOCUMENT, Injectable, computed, inject, signal } from '@angular/core';

/** El header por el que la API acepta el token. El único lugar donde viaja. */
export const TOKEN_HEADER = 'X-PromptBrief-Token';

/** El query param por el que llega en la carga del documento, y solo ahí. */
export const TOKEN_PARAM = 'token';

/**
 * El token de la sesión, en memoria.
 *
 * Llega en la URL porque el navegador no puede poner un header custom en la carga del
 * documento, y se va de la URL en el mismo instante: si queda, se lo lleva el historial
 * —y con él cualquier backup o sincronización del perfil del navegador— para toda la
 * vida del token.
 *
 * Tampoco se guarda en `localStorage`: el token muere con el proceso que lo imprimió,
 * así que persistirlo solo dejaría uno vencido dando vueltas.
 */
@Injectable({ providedIn: 'root' })
export class Session {
  private readonly document = inject(DOCUMENT);
  private readonly captured = signal<string | null>(null);

  readonly token = this.captured.asReadonly();
  readonly present = computed(() => this.captured() !== null);

  /**
   * Se queda con el token de `location.search` y lo borra de la barra de direcciones.
   *
   * Corre una sola vez, al arrancar la aplicación. Usa `replaceState` y no `pushState`
   * para no dejar la URL con token como una entrada del historial a la que se vuelve
   * con el botón de atrás.
   */
  capture(): void {
    const view = this.document.defaultView;
    if (!view) {
      return;
    }

    const url = new URL(view.location.href);
    const token = url.searchParams.get(TOKEN_PARAM);
    if (!token) {
      return;
    }

    this.captured.set(token);
    url.searchParams.delete(TOKEN_PARAM);
    view.history.replaceState(view.history.state, '', `${url.pathname}${url.search}${url.hash}`);
  }
}
