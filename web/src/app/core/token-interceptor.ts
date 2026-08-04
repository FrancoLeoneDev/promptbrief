import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { TOKEN_HEADER, Session } from './session';

/** El prefijo de la API. Lo demás son los estáticos del propio front. */
const API_PREFIX = '/api/';

/**
 * Le cuelga el token de la sesión a cada llamada de la API.
 *
 * Solo a las rutas relativas que empiezan con `/api/`. La condición no es decorativa:
 * una URL absoluta apunta a otro origen, y mandarle el header ahí regalaría el token a
 * quien haya elegido esa URL. Como el front nunca llama afuera, la guarda cuesta nada y
 * cierra la única forma en que el token podría salir de la máquina.
 *
 * Sin token no se cancela el pedido: sale igual y vuelve un 401, que es lo que la UI
 * necesita para decir "la sesión no vale" en vez de quedarse en blanco.
 */
export const tokenInterceptor: HttpInterceptorFn = (request, next) => {
  const token = inject(Session).token();
  if (token === null || !request.url.startsWith(API_PREFIX)) {
    return next(request);
  }
  return next(request.clone({ setHeaders: { [TOKEN_HEADER]: token } }));
};
