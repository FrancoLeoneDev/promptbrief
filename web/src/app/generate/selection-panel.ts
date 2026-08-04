import { Component, input } from '@angular/core';

import { Selection, Slot, slotLabel } from '../core/models';

interface Group {
  title: string;
  reason: string;
  tone: 'ok' | 'warning' | 'muted';
  slots: Slot[];
}

/**
 * Qué del perfil entró al brief y qué quedó afuera, con el motivo.
 *
 * Los cuatro grupos son el motivo: el servidor los manda separados justamente para que
 * "no aplica a esta tarea" no se lea como una pérdida. Solo `over_budget` es algo que el
 * usuario puede querer resolver, y es el único que sugiere una acción.
 */
@Component({
  selector: 'app-selection-panel',
  templateUrl: './selection-panel.html',
  styleUrl: './selection-panel.css',
})
export class SelectionPanel {
  readonly selection = input.required<Selection>();

  protected readonly slotLabel = slotLabel;

  protected groups(): Group[] {
    const selection = this.selection();
    return [
      {
        title: 'Inyectado',
        reason: 'Entró al brief.',
        tone: 'ok',
        slots: selection.selected,
      },
      {
        title: 'Fuera de presupuesto',
        reason: 'No entró en el presupuesto de atención. Subí budget_tokens en el perfil.',
        tone: 'warning',
        slots: selection.over_budget,
      },
      {
        title: 'No aplica',
        reason: 'El dato está marcado para otros tipos de tarea.',
        tone: 'muted',
        slots: selection.not_applicable,
      },
      {
        title: 'Sin revisar',
        reason: 'La destilación no lo pudo clasificar, así que no se inyecta.',
        tone: 'muted',
        slots: selection.skipped_for_review,
      },
    ];
  }
}
