import { Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { Api } from '../core/api';
import { Call } from '../core/call';
import { checkedOf, textOf } from '../core/dom';
import {
  Profile,
  ProfileDiff,
  SLOT_KINDS,
  Slot,
  SlotKind,
  TASK_TYPES,
  TaskType,
  counted,
  slotLabel,
  taskTypeLabel,
} from '../core/models';
import { SyncPanel } from './sync-panel';

/**
 * El editor de un perfil: el contenido destilado, con su procedencia a la vista.
 *
 * Guardar manda el perfil **entero** a `POST /api/profiles`, que reemplaza. Por eso el
 * borrador es una copia completa de lo que llegó y no un diccionario de cambios: mandar
 * menos de lo que se leyó sería borrar lo que no se tocó.
 */
@Component({
  selector: 'app-profile-editor-page',
  imports: [RouterLink, SyncPanel],
  templateUrl: './profile-editor-page.html',
  styleUrl: './profile-editor-page.css',
})
export class ProfileEditorPage {
  private readonly api = inject(Api);

  /**
   * El nombre sale del snapshot: a esta pantalla se entra desde la lista, nunca de un
   * perfil a otro, así que el componente se construye de nuevo con cada nombre.
   */
  protected readonly name = inject(ActivatedRoute).snapshot.paramMap.get('name') ?? '';

  protected readonly loaded = new Call<Profile>();
  protected readonly saving = new Call<Profile>();
  protected readonly syncing = new Call<ProfileDiff>();
  protected readonly applying = new Call<Profile>();

  protected readonly draft = signal<Profile | null>(null);
  protected readonly dirty = signal(false);
  /** La última versión que confirmó el servidor: es a donde vuelve "descartar". */
  private readonly saved = signal<Profile | null>(null);
  protected readonly needingReview = computed(
    () => this.draft()?.slots.filter((slot) => slot.needs_review).length ?? 0,
  );

  protected readonly kinds = SLOT_KINDS;
  protected readonly taskTypes = TASK_TYPES;
  protected readonly slotLabel = slotLabel;
  protected readonly taskTypeLabel = taskTypeLabel;
  protected readonly counted = counted;
  protected readonly textOf = textOf;
  protected readonly checkedOf = checkedOf;

  constructor() {
    this.load();
  }

  protected load(): void {
    this.loaded.run(this.api.profile(this.name), (profile) => this.adopt(profile));
  }

  protected save(): void {
    const draft = this.draft();
    if (draft) {
      this.saving.run(this.api.save(draft), (profile) => this.adopt(profile));
    }
  }

  protected discard(): void {
    const original = this.saved();
    if (original) {
      this.adopt(original);
    }
  }

  protected sync(): void {
    this.syncing.run(this.api.sync(this.name));
  }

  /**
   * Aplica lo que mostró la comparación: vuelve a destilar el proyecto, esta vez
   * escribiendo. Es un `scan` con `force` porque el preview, por diseño, no escribe.
   */
  protected applySync(): void {
    const profile = this.draft();
    if (!profile) {
      return;
    }
    this.applying.run(
      this.api.scan({ root: profile.root, name: profile.name, force: true }),
      (fresh) => {
        this.adopt(fresh);
        this.syncing.clear();
      },
    );
  }

  protected patchSlot(index: number, patch: Partial<Slot>): void {
    const draft = this.draft();
    if (!draft) {
      return;
    }
    const slots = draft.slots.map((slot, at) => (at === index ? { ...slot, ...patch } : slot));
    this.draft.set({ ...draft, slots });
    this.dirty.set(true);
  }

  protected toggleAppliesTo(index: number, task: TaskType, on: boolean): void {
    const current = this.draft()?.slots[index]?.applies_to ?? [];
    const applies_to = on
      ? this.taskTypes.filter((each) => each === task || current.includes(each))
      : current.filter((each) => each !== task);
    this.patchSlot(index, { applies_to });
  }

  protected setKind(index: number, kind: string): void {
    this.patchSlot(index, { kind: kind as SlotKind });
  }

  private adopt(profile: Profile): void {
    // El borrador es una copia: `saved` tiene que quedarse con lo que devolvió el
    // servidor, intacto, para que "descartar" tenga a dónde volver.
    this.saved.set(profile);
    this.draft.set(structuredClone(profile));
    this.dirty.set(false);
  }
}
