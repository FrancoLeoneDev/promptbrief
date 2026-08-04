import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { Api, apiMessage } from './api';
import { Profile } from './models';

describe('Api', () => {
  let api: Api;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(Api);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('pide la lista de perfiles al endpoint de resumen', () => {
    api.profiles().subscribe();
    http.expectOne({ method: 'GET', url: '/api/profiles' }).flush([]);
  });

  it('escapa el nombre del perfil en la ruta', () => {
    // Un nombre puede traer lo que el usuario tipeó; sin escapar, una barra lo partiría
    // en dos segmentos y pegaría contra otro endpoint.
    api.profile('con espacio/y barra').subscribe();
    http.expectOne('/api/profiles/con%20espacio%2Fy%20barra').flush({});
  });

  it('escanea mandando la raíz y el nombre opcional', () => {
    api.scan({ root: 'C:/proj', name: 'proj', force: true }).subscribe();
    const request = http.expectOne({ method: 'POST', url: '/api/profiles/scan' });
    expect(request.request.body).toEqual({ root: 'C:/proj', name: 'proj', force: true });
  });

  it('guarda el perfil entero, no un parche', () => {
    // `POST /api/profiles` reemplaza: mandar menos de lo que se leyó borra slots.
    const profile: Profile = {
      name: 'proj',
      root: 'C:/proj',
      budget_tokens: 1500,
      sources: [{ path: 'CLAUDE.md', sha256: 'abc' }],
      slots: [],
    };
    api.save(profile).subscribe();
    expect(http.expectOne({ method: 'POST', url: '/api/profiles' }).request.body).toEqual(profile);
  });

  it('sincroniza contra la ruta del perfil y no escribe nada', () => {
    api.sync('proj').subscribe();
    http.expectOne({ method: 'POST', url: '/api/profiles/proj/sync' }).flush({});
  });

  it('borra con DELETE', () => {
    api.remove('proj').subscribe();
    http.expectOne({ method: 'DELETE', url: '/api/profiles/proj' }).flush(null);
  });

  it('manda el pedido de lint tal como lo armó la pantalla', () => {
    api
      .lint({ text: 'algo', profile_name: 'proj', constraints: ['no tocar el build'] })
      .subscribe();
    const request = http.expectOne({ method: 'POST', url: '/api/lint' });
    expect(request.request.body).toEqual({
      text: 'algo',
      profile_name: 'proj',
      constraints: ['no tocar el build'],
    });
  });

  it('pide el brief al endpoint que lo renderiza', () => {
    api.brief({ text: 'algo' }).subscribe();
    http.expectOne({ method: 'POST', url: '/api/brief' }).flush({ text: '<brief/>' });
  });
});

describe('apiMessage', () => {
  it('muestra el detalle que escribió el servidor', () => {
    const error = new HttpErrorResponse({ status: 403, error: { detail: 'Ruta no permitida.' } });
    expect(apiMessage(error)).toBe('Ruta no permitida.');
  });

  it('junta los errores de validación de FastAPI', () => {
    const error = new HttpErrorResponse({
      status: 422,
      error: { detail: [{ msg: 'falta text' }, { msg: 'root inválido' }] },
    });
    expect(apiMessage(error)).toBe('falta text. root inválido');
  });

  it('explica un 401 en términos de la sesión', () => {
    expect(apiMessage(new HttpErrorResponse({ status: 401 }))).toContain('pbrief serve');
  });

  it('distingue el servidor caído del servidor que contestó', () => {
    expect(apiMessage(new HttpErrorResponse({ status: 0 }))).toContain('pbrief serve');
    expect(apiMessage(new HttpErrorResponse({ status: 500 }))).toContain('500');
  });
});
