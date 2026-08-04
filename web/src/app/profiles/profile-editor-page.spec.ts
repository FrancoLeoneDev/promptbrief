import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';

import { Profile, ProfileDiff, Slot } from '../core/models';
import { ProfileEditorPage } from './profile-editor-page';

const NAME = 'demo';

function slot(over: Partial<Slot>): Slot {
  return {
    id: 'stack.0',
    kind: 'stack',
    content: 'Next.js con export estático',
    applies_to: [],
    source: { file: 'CLAUDE.md', line: 3 },
    needs_review: false,
    redacted: false,
    ...over,
  };
}

const PLAIN_SLOT = slot({});
const REVIEW_SLOT = slot({
  id: 'unclassified.0',
  kind: 'unclassified',
  content: 'algo que no se supo clasificar',
  needs_review: true,
  source: null,
});

function profile(over: Partial<Profile> = {}): Profile {
  return {
    name: NAME,
    root: 'C:/proj/demo',
    budget_tokens: 2000,
    sources: [{ path: 'CLAUDE.md', sha256: 'a'.repeat(64) }],
    slots: [PLAIN_SLOT],
    ...over,
  };
}

function diff(over: Partial<ProfileDiff> = {}): ProfileDiff {
  return { added: [], removed: [], modified: [], unchanged: [PLAIN_SLOT], ...over };
}

describe('ProfileEditorPage', () => {
  let fixture: ComponentFixture<ProfileEditorPage>;
  let http: HttpTestingController;
  let page: HTMLElement;

  async function click(label: string): Promise<void> {
    const button = [...page.querySelectorAll('button')].find((each) =>
      each.textContent?.includes(label),
    );
    button!.click();
    await fixture.whenStable();
  }

  async function type(selector: string, value: string): Promise<void> {
    const field = page.querySelector(selector) as HTMLTextAreaElement;
    field.value = value;
    field.dispatchEvent(new Event('input'));
    await fixture.whenStable();
  }

  async function loadWith(loaded: Profile): Promise<void> {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({ name: NAME }) } },
        },
      ],
    });
    fixture = TestBed.createComponent(ProfileEditorPage);
    http = TestBed.inject(HttpTestingController);
    page = fixture.nativeElement as HTMLElement;

    await fixture.whenStable();
    http.expectOne(`/api/profiles/${NAME}`).flush(loaded);
    await fixture.whenStable();
  }

  afterEach(() => http.verify());

  it('llama a scan con force y con el root del perfil al aplicar la sincronización', async () => {
    await loadWith(profile());

    await click('Comparar con el disco');
    http.expectOne(`/api/profiles/${NAME}/sync`).flush(diff({ added: [REVIEW_SLOT] }));
    await fixture.whenStable();

    await click('Volver a destilar y guardar');
    const request = http.expectOne('/api/profiles/scan');
    expect(request.request.body).toEqual({ root: 'C:/proj/demo', name: NAME, force: true });

    request.flush(profile({ slots: [PLAIN_SLOT, REVIEW_SLOT] }));
    await fixture.whenStable();

    // Aplicar adopta la respuesta fresca como guardada: no debería quedar "sin guardar".
    expect(page.textContent).not.toContain('Hay cambios sin guardar');
  });

  it('marca sucio al editar, descartar vuelve a lo guardado y guardar limpia el flag', async () => {
    await loadWith(profile());

    await type('textarea', 'contenido editado a mano');
    expect(page.textContent).toContain('Hay cambios sin guardar');

    const saveButton = [...page.querySelectorAll('button')].find((each) =>
      each.textContent?.includes('Guardar'),
    ) as HTMLButtonElement;
    expect(saveButton.disabled).toBe(false);

    await click('Descartar cambios');
    expect(page.textContent).not.toContain('Hay cambios sin guardar');
    expect((page.querySelector('textarea') as HTMLTextAreaElement).value).toBe(PLAIN_SLOT.content);

    await type('textarea', 'otra edición');
    expect(page.textContent).toContain('Hay cambios sin guardar');

    await click('Guardar');
    const request = http.expectOne('/api/profiles');
    request.flush(profile({ slots: [slot({ content: 'otra edición' })] }));
    await fixture.whenStable();

    expect(page.textContent).not.toContain('Hay cambios sin guardar');
  });

  it('prende y apaga un tipo de tarea en applies_to', async () => {
    // TASK_TYPES es ['code_change', 'debug', 'writing'], mismo orden que se dibujan.
    await loadWith(profile({ slots: [slot({ applies_to: ['code_change'] })] }));

    const checkboxes = () =>
      [...page.querySelectorAll('.control.wide input[type="checkbox"]')] as HTMLInputElement[];

    async function toggle(index: number, checked: boolean): Promise<void> {
      const box = checkboxes()[index];
      box.checked = checked;
      box.dispatchEvent(new Event('change'));
      await fixture.whenStable();
    }

    expect(checkboxes().map((box) => box.checked)).toEqual([true, false, false]);

    // Prender "writing" (índice 2): se agrega sin sacar el que ya estaba.
    await toggle(2, true);
    expect(checkboxes().map((box) => box.checked)).toEqual([true, false, true]);

    // Apagar "code_change" (índice 0): solo se saca ese, "writing" queda.
    await toggle(0, false);
    expect(checkboxes().map((box) => box.checked)).toEqual([false, false, true]);
  });

  it('muestra un slot con needs_review distinto y con su explicación', async () => {
    await loadWith(profile({ slots: [PLAIN_SLOT, REVIEW_SLOT] }));

    const items = [...page.querySelectorAll('li.slot')];
    expect(items).toHaveLength(2);

    const plain = items[0];
    const flagged = items[1];

    expect(flagged.classList).toContain('needs-review');
    expect(plain.classList).not.toContain('needs-review');

    expect(flagged.textContent).toContain('no se inyecta');
    expect(plain.textContent).not.toContain('no se inyecta');
  });
});
