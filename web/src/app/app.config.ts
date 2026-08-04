import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  ApplicationConfig,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter, withInMemoryScrolling } from '@angular/router';

import { routes } from './app.routes';
import { Session } from './core/session';
import { tokenInterceptor } from './core/token-interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    // El token se rescata antes que nada: la primera pantalla ya pide datos, y un
    // pedido que saliera sin el header volvería con un 401 evitable.
    provideAppInitializer(() => inject(Session).capture()),
    provideRouter(routes, withInMemoryScrolling({ scrollPositionRestoration: 'top' })),
    provideHttpClient(withInterceptors([tokenInterceptor])),
  ],
};
