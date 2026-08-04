import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { DOCUMENT } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { Api } from './api';
import { TOKEN_HEADER, Session } from './session';
import { tokenInterceptor } from './token-interceptor';

const TOKEN = 'un-token-de-sesion';

/**
 * Levanta el inyector con un `window` de mentira: la URL con la que se abrió el
 * documento y un historial que anota lo que le pidieron reescribir.
 */
function open(href: string) {
  const replaced: string[] = [];
  const view = {
    location: { href },
    history: {
      state: null,
      replaceState: (_state: unknown, _title: string, url: string) => {
        replaced.push(url);
      },
    },
  };

  TestBed.configureTestingModule({
    providers: [
      { provide: DOCUMENT, useValue: { defaultView: view } },
      provideHttpClient(withInterceptors([tokenInterceptor])),
      provideHttpClientTesting(),
    ],
  });

  const session = TestBed.inject(Session);
  session.capture();
  return { replaced, session, http: TestBed.inject(HttpTestingController) };
}

describe('tokenInterceptor', () => {
  it('manda el token en el header que exige la API', () => {
    const { http } = open(`http://127.0.0.1:8765/?token=${TOKEN}`);

    TestBed.inject(Api).health().subscribe();

    const request = http.expectOne('/api/health');
    expect(request.request.headers.get(TOKEN_HEADER)).toBe(TOKEN);
    request.flush({ status: 'ok' });
    http.verify();
  });

  it('no manda el token a un origen ajeno', () => {
    // Es la única forma en que el token podría salir de la máquina.
    const { http } = open(`http://127.0.0.1:8765/?token=${TOKEN}`);

    TestBed.inject(HttpClient).get('https://ejemplo.invalid/api/health').subscribe();

    const request = http.expectOne('https://ejemplo.invalid/api/health');
    expect(request.request.headers.has(TOKEN_HEADER)).toBe(false);
    request.flush({});
    http.verify();
  });

  it('deja pasar el pedido sin header cuando no hubo token en la URL', () => {
    // Sale igual y vuelve un 401: es lo que la UI necesita para decir que la sesión no
    // vale, en vez de quedarse esperando para siempre.
    const { http } = open('http://127.0.0.1:8765/');

    TestBed.inject(Api).health().subscribe();

    const request = http.expectOne('/api/health');
    expect(request.request.headers.has(TOKEN_HEADER)).toBe(false);
    request.flush({ status: 'ok' });
    http.verify();
  });
});

describe('Session', () => {
  it('se queda con el token y lo borra de la barra de direcciones', () => {
    // Si queda en la URL, se lo lleva el historial del navegador para siempre.
    const { session, replaced } = open(`http://127.0.0.1:8765/generate?token=${TOKEN}&otro=1`);

    expect(session.token()).toBe(TOKEN);
    expect(session.present()).toBe(true);
    expect(replaced).toEqual(['/generate?otro=1']);
  });

  it('no toca la URL cuando no hay token que sacar', () => {
    const { session, replaced } = open('http://127.0.0.1:8765/profiles');

    expect(session.token()).toBeNull();
    expect(session.present()).toBe(false);
    expect(replaced).toEqual([]);
  });
});
