import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Api } from '../core/api';
import { Call } from '../core/call';
import { checkedOf, textOf } from '../core/dom';
import { Profile, ProfileSummary, counted } from '../core/models';

/**
 * La lista de perfiles y el formulario que crea uno nuevo.
 *
 * Escanear es la única forma de crear un perfil: `POST /api/profiles` solo edita uno que
 * ya existe. Por eso el formulario de escaneo vive acá arriba y no escondido en el
 * editor.
 */
@Component({
  selector: 'app-profiles-page',
  imports: [RouterLink],
  templateUrl: './profiles-page.html',
  styleUrl: './profiles-page.css',
})
export class ProfilesPage {
  private readonly api = inject(Api);

  protected readonly profiles = new Call<ProfileSummary[]>();
  protected readonly scanning = new Call<Profile>();
  protected readonly removing = new Call<void>();

  protected readonly root = signal('');
  protected readonly name = signal('');
  protected readonly force = signal(false);
  /** El perfil cuyo borrado está esperando confirmación. */
  protected readonly confirming = signal<string | null>(null);

  protected readonly textOf = textOf;
  protected readonly checkedOf = checkedOf;
  protected readonly counted = counted;

  constructor() {
    this.reload();
  }

  protected reload(): void {
    this.profiles.run(this.api.profiles());
  }

  protected scan(event: Event): void {
    event.preventDefault();
    const root = this.root().trim();
    if (!root) {
      return;
    }

    const name = this.name().trim();
    this.scanning.run(this.api.scan({ root, name: name || null, force: this.force() }), () => {
      this.root.set('');
      this.name.set('');
      this.force.set(false);
      this.reload();
    });
  }

  protected remove(name: string): void {
    this.removing.run(this.api.remove(name), () => {
      this.confirming.set(null);
      this.reload();
    });
  }
}
