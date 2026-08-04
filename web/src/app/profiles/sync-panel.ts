import { Component, computed, input, output } from '@angular/core';

import { ProfileDiff, counted, slotLabel } from '../core/models';

/**
 * Qué cambió en el proyecto desde el último escaneo.
 *
 * Es solo un preview: `POST /sync` no escribe nada. Aplicar vuelve a destilar con
 * `force`, y eso pisa las ediciones manuales, así que el botón lo dice antes.
 */
@Component({
  selector: 'app-sync-panel',
  templateUrl: './sync-panel.html',
  styleUrl: './sync-panel.css',
})
export class SyncPanel {
  readonly diff = input.required<ProfileDiff>();
  readonly applying = input(false);
  readonly apply = output<void>();
  readonly dismiss = output<void>();

  protected readonly slotLabel = slotLabel;
  protected readonly counted = counted;

  protected readonly changes = computed(() => {
    const diff = this.diff();
    return diff.added.length + diff.removed.length + diff.modified.length;
  });
}
