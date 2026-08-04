import { signal } from '@angular/core';
import { Observable } from 'rxjs';

import { apiMessage } from './api';

/**
 * Una llamada a la API con sus tres estados en señales.
 *
 * Existe para que ninguna pantalla vuelva a escribir el trío pendiente/valor/error a
 * mano: son cinco pantallas y once endpoints, y la versión copiada se desincroniza en
 * cuanto una olvide apagar `pending` en el camino del error.
 *
 * No se desuscribe: `HttpClient` completa después de una emisión y el pedido se cancela
 * solo si nadie lo escucha, así que no hay nada colgado que limpiar.
 */
export class Call<T> {
  private readonly _value = signal<T | null>(null);
  private readonly _error = signal<string | null>(null);
  private readonly _pending = signal(false);

  readonly value = this._value.asReadonly();
  readonly error = this._error.asReadonly();
  readonly pending = this._pending.asReadonly();

  run(source: Observable<T>, done?: (value: T) => void): void {
    this._pending.set(true);
    this._error.set(null);
    source.subscribe({
      next: (value) => {
        this._value.set(value);
        this._pending.set(false);
        done?.(value);
      },
      error: (error: unknown) => {
        this._error.set(apiMessage(error));
        this._pending.set(false);
      },
    });
  }

  clear(): void {
    this._value.set(null);
    this._error.set(null);
    this._pending.set(false);
  }
}
