import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  BriefRequest,
  BriefResult,
  LintResult,
  Profile,
  ProfileDiff,
  ProfileSummary,
  ScanRequest,
} from './models';

/**
 * El único lugar del front que conoce las rutas de la API.
 *
 * No hay acceso al disco por ningún otro lado: escanear, guardar y leer un perfil pasa
 * siempre por acá, que es lo que mantiene la allowlist del servidor como la única
 * autoridad sobre qué directorios se pueden tocar.
 */
@Injectable({ providedIn: 'root' })
export class Api {
  private readonly http = inject(HttpClient);

  health(): Observable<{ status: string }> {
    return this.http.get<{ status: string }>('/api/health');
  }

  profiles(): Observable<ProfileSummary[]> {
    return this.http.get<ProfileSummary[]>('/api/profiles');
  }

  profile(name: string): Observable<Profile> {
    return this.http.get<Profile>(this.at(name));
  }

  scan(request: ScanRequest): Observable<Profile> {
    return this.http.post<Profile>('/api/profiles/scan', request);
  }

  save(profile: Profile): Observable<Profile> {
    return this.http.post<Profile>('/api/profiles', profile);
  }

  remove(name: string): Observable<void> {
    return this.http.delete<void>(this.at(name));
  }

  /** Previsualiza una destilación fresca. No escribe: aplicar es un `scan` con `force`. */
  sync(name: string): Observable<ProfileDiff> {
    return this.http.post<ProfileDiff>(`${this.at(name)}/sync`, {});
  }

  lint(request: BriefRequest): Observable<LintResult> {
    return this.http.post<LintResult>('/api/lint', request);
  }

  brief(request: BriefRequest): Observable<BriefResult> {
    return this.http.post<BriefResult>('/api/brief', request);
  }

  /** El nombre va escapado: es un segmento de ruta y puede traer lo que el usuario tipeó. */
  private at(name: string): string {
    return `/api/profiles/${encodeURIComponent(name)}`;
  }
}

/**
 * El mensaje que la API mandó, o uno que explique el silencio.
 *
 * El backend contesta `{"detail": "..."}` en cada 4xx y esos textos ya están escritos
 * para que los lea una persona, así que se muestran tal cual en vez de traducirlos a un
 * catálogo propio que se desincronizaría con el servidor.
 */
export function apiMessage(error: unknown): string {
  if (!(error instanceof HttpErrorResponse)) {
    return 'Algo falló antes de llegar al servidor.';
  }

  const detail: unknown = error.error?.detail;
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail)) {
    // El 422 de FastAPI: una lista de errores de validación, uno por campo.
    return detail.map((item) => String(item?.msg ?? item)).join('. ');
  }
  if (error.status === 0) {
    return 'No hubo respuesta. Fijate si el proceso de pbrief serve sigue vivo.';
  }
  if (error.status === 401) {
    return 'La sesión no vale. Abrí de nuevo la URL con token que imprimió pbrief serve.';
  }
  return `El servidor respondió ${error.status}.`;
}
