import { DOCUMENT, Component, computed, inject, signal } from '@angular/core';

import { Api } from '../core/api';
import { Call } from '../core/call';
import { textOf } from '../core/dom';
import {
  BriefRequest,
  BriefResult,
  Finding,
  LintResult,
  ProfileSummary,
  isListSlot,
  taskTypeLabel,
} from '../core/models';
import { SelectionPanel } from './selection-panel';

/** Un campo del interrogatorio: el hallazgo que lo pidió y si sigue abierto. */
export interface Question {
  slot: string;
  finding: Finding;
  answered: boolean;
}

/**
 * El generador: texto suelto adentro, brief estructurado afuera.
 *
 * El formulario del medio no está escrito en ningún lado. Sale de los hallazgos del
 * lint: cada uno que trae `slot_name` nombra el campo que falta, y el `message` y la
 * `suggestion` son su etiqueta y su ayuda. Por eso una regla nueva en el backend estrena
 * su campo sin tocar una línea de acá, y por eso no hay ninguna tabla de `rule_id` a
 * campo — sería una segunda fuente de verdad de algo que ya viaja resuelto.
 */
@Component({
  selector: 'app-generate-page',
  imports: [SelectionPanel],
  templateUrl: './generate-page.html',
  styleUrl: './generate-page.css',
})
export class GeneratePage {
  private readonly api = inject(Api);
  private readonly document = inject(DOCUMENT);

  protected readonly profiles = new Call<ProfileSummary[]>();
  protected readonly linting = new Call<LintResult>();
  protected readonly generating = new Call<BriefResult>();

  protected readonly text = signal('');
  protected readonly profileName = signal('');
  protected readonly answers = signal<Record<string, string | string[]>>({});
  protected readonly copied = signal(false);

  /** El último análisis, venga del lint o del brief: los dos devuelven lo mismo. */
  private readonly report = signal<LintResult | null>(null);
  /**
   * El último hallazgo visto de cada campo.
   *
   * Se acumula porque un campo contestado deja de aparecer entre los hallazgos —para eso
   * se contesta—, y su etiqueta tiene que sobrevivir a eso o el valor cargado quedaría
   * flotando sin decir de qué es.
   */
  private readonly seen = signal<Record<string, Finding>>({});

  protected readonly taskType = computed(() => this.report()?.task_type ?? null);

  /** Los hallazgos que no nombran ningún campo: defectos del texto, no faltantes. */
  protected readonly remarks = computed(
    () => this.report()?.findings.filter((finding) => finding.slot_name === null) ?? [],
  );

  protected readonly questions = computed<Question[]>(() => {
    const open = new Set(
      this.report()
        ?.findings.map((finding) => finding.slot_name)
        .filter((slot): slot is string => slot !== null) ?? [],
    );
    const answered = Object.keys(this.answers()).filter((slot) => this.filled(slot));
    const seen = this.seen();

    return [...new Set([...open, ...answered])]
      .filter((slot) => seen[slot] !== undefined)
      .map((slot) => ({ slot, finding: seen[slot], answered: !open.has(slot) }));
  });

  protected readonly isListSlot = isListSlot;
  protected readonly taskTypeLabel = taskTypeLabel;
  protected readonly textOf = textOf;

  constructor() {
    this.profiles.run(this.api.profiles());
  }

  protected analyze(): void {
    this.linting.run(this.api.lint(this.request()), (result) => this.absorb(result));
  }

  protected generate(): void {
    this.generating.run(this.api.brief(this.request()), (result) => {
      // El brief trae los hallazgos ya recalculados: el interrogatorio se actualiza con
      // la misma respuesta, sin una segunda vuelta contra el lint.
      this.absorb(result);
      this.copied.set(false);
    });
  }

  protected copy(text: string): void {
    const clipboard = this.document.defaultView?.navigator.clipboard;
    if (!clipboard) {
      return;
    }
    void clipboard.writeText(text).then(() => this.copied.set(true));
  }

  // --- respuestas del interrogatorio ---------------------------------------

  protected answerOf(slot: string): string {
    const value = this.answers()[slot];
    return typeof value === 'string' ? value : '';
  }

  protected rowsOf(slot: string): string[] {
    const value = this.answers()[slot];
    const rows = Array.isArray(value) ? value : [];
    // Siempre una fila vacía a la vista: sin eso, un campo de lista recién abierto no
    // tendría dónde escribir.
    return rows.length > 0 ? rows : [''];
  }

  protected answer(slot: string, value: string): void {
    this.answers.update((answers) => ({ ...answers, [slot]: value }));
  }

  protected answerRow(slot: string, index: number, value: string): void {
    const rows = [...this.rowsOf(slot)];
    rows[index] = value;
    this.answers.update((answers) => ({ ...answers, [slot]: rows }));
  }

  protected addRow(slot: string): void {
    this.answers.update((answers) => ({ ...answers, [slot]: [...this.rowsOf(slot), ''] }));
  }

  protected removeRow(slot: string, index: number): void {
    const rows = this.rowsOf(slot).filter((_, at) => at !== index);
    this.answers.update((answers) => ({ ...answers, [slot]: rows }));
  }

  // --- armado del pedido ---------------------------------------------------

  /**
   * El cuerpo que van a recibir tanto `/api/lint` como `/api/brief`.
   *
   * Las respuestas se copian **por su `slot_name`**, sin traducir: la clave que mandó el
   * servidor es la clave del campo del pedido, y esa coincidencia es justamente lo que
   * hace que el formulario no necesite saber nada de las reglas.
   */
  private request(): BriefRequest {
    const request: BriefRequest = { text: this.text() };
    const profile = this.profileName();
    if (profile) {
      request.profile_name = profile;
    }

    for (const [slot, value] of Object.entries(this.answers())) {
      if (Array.isArray(value)) {
        const items = value.map((item) => item.trim()).filter((item) => item.length > 0);
        if (items.length > 0) {
          request[slot] = items;
        }
      } else if (value.trim().length > 0) {
        request[slot] = value.trim();
      }
    }
    return request;
  }

  private absorb(result: LintResult): void {
    this.report.set(result);
    this.seen.update((seen) => {
      const merged = { ...seen };
      for (const finding of result.findings) {
        if (finding.slot_name !== null) {
          merged[finding.slot_name] = finding;
        }
      }
      return merged;
    });
  }

  private filled(slot: string): boolean {
    const value = this.answers()[slot];
    return Array.isArray(value)
      ? value.some((item) => item.trim().length > 0)
      : (value ?? '').trim().length > 0;
  }
}
