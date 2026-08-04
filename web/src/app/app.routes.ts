import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'profiles' },
  {
    path: 'profiles',
    title: 'Perfiles - PromptBrief',
    loadComponent: () => import('./profiles/profiles-page').then((m) => m.ProfilesPage),
  },
  {
    path: 'profiles/:name',
    title: 'Perfil - PromptBrief',
    loadComponent: () => import('./profiles/profile-editor-page').then((m) => m.ProfileEditorPage),
  },
  {
    path: 'generate',
    title: 'Generador - PromptBrief',
    loadComponent: () => import('./generate/generate-page').then((m) => m.GeneratePage),
  },
  { path: '**', redirectTo: 'profiles' },
];
